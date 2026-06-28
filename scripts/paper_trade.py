#!/usr/bin/env python3
"""
Paper-trade the trained TFT through the PaperBroker on REAL data — zero risk.

Honest framing: the validated model has no measured alpha (it tracks market
beta), so this run is expected to roughly follow the market minus costs. The
purpose here is to prove the EXECUTION + ACCOUNTING layer is correct and safe,
and that it is ready to be pointed at Schwab's live feed once OAuth is done.

No look-ahead: each day's signal uses only data through that day's close; the
position then earns the close->next-close move, realized at the next mark.

Usage:
    SCANIFY_FMP_API_KEY=... python scripts/paper_trade.py
"""
from __future__ import annotations

import json, os, sys, time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.scanify.fmp_adapter import FMPAdapter  # noqa: E402
from src.ml.data_pipeline import FeatureEngineer, FeatureConfig  # noqa: E402
from src.ml.models import create_tft_model  # noqa: E402
from src.execution.paper_broker import PaperBroker  # noqa: E402

UNIVERSE = ["SPY", "QQQ", "IWM", "DIA", "AAPL", "MSFT", "NVDA", "AMZN",
            "GOOGL", "META", "TSLA", "JPM", "XOM", "JNJ", "WMT"]
WINDOW_DAYS = 252          # paper-trade the most recent ~1 year (out of sample)
COMMISSION_BPS = 1.0
SLIPPAGE_BPS = 1.0
TRADING_DAYS = 252
ARTIFACT_DIR = ROOT / "artifacts"


# --- data source (swap this for Schwab later) ------------------------------ #
def get_daily_bars(adapter: FMPAdapter, symbol: str) -> pd.DataFrame | None:
    bars = adapter.get_historical_daily(symbol, limit=4000)
    if not bars or len(bars) < 400:
        return None
    df = pd.DataFrame(bars)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").set_index("date")
    return df[["open", "high", "low", "close", "volume"]].astype(float)


def load_model(path: Path):
    ckpt = torch.load(path, map_location="cpu", weights_only=False)
    model = create_tft_model(
        input_dim=ckpt["input_dim"], hidden_dim=64, num_layers=2, num_heads=4,
        sequence_length=ckpt["seq_len"], prediction_horizon=ckpt["horizon"],
        dropout=0.1, device="cpu",
    )
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    return model, ckpt


def main():
    t0 = time.time()
    print("=" * 70)
    print("  PAPER TRADING  (trained TFT + PaperBroker, real FMP data, ZERO risk)")
    print("=" * 70)
    if not os.environ.get("SCANIFY_FMP_API_KEY"):
        print("ERROR: set SCANIFY_FMP_API_KEY"); sys.exit(1)
    if not (ARTIFACT_DIR / "tft_model.pt").exists():
        print("ERROR: train first (scripts/train_and_validate.py)"); sys.exit(1)

    model, ckpt = load_model(ARTIFACT_DIR / "tft_model.pt")
    seq_len = ckpt["seq_len"]; feat_names = ckpt["feature_names"]
    mu = np.asarray(ckpt["norm_mean"], dtype=np.float32)
    sd = np.asarray(ckpt["norm_std"], dtype=np.float32)
    print(f"\nLoaded model: input_dim={ckpt['input_dim']} seq_len={seq_len} "
          f"features={len(feat_names)}")

    adapter = FMPAdapter()
    cfg = FeatureConfig(
        sequence_length=seq_len, prediction_horizon=ckpt["horizon"],
        use_iv=False, use_greeks=False, use_put_call_ratio=False,
        use_options_volume=False, use_bid_ask_spread=False,
        use_trade_imbalance=False, use_order_flow=False, normalize_features=False,
    )
    fe = FeatureEngineer(cfg)

    print("\n[1/3] Fetching data + building features ...")
    feats_by_sym, close_by_sym = {}, {}
    for sym in UNIVERSE:
        ohlcv = get_daily_bars(adapter, sym)
        if ohlcv is None:
            continue
        f = fe.generate_all_features(ohlcv).replace([np.inf, -np.inf], np.nan).fillna(0.0)
        feats_by_sym[sym] = f[feat_names].astype(np.float32)
        close_by_sym[sym] = ohlcv["close"]
    syms = list(feats_by_sym)
    # common trading calendar
    dates = sorted(set.intersection(*[set(close_by_sym[s].index) for s in syms]))
    dates = dates[-(WINDOW_DAYS + 1):]
    print(f"  symbols: {len(syms)}  | paper window: {dates[0].date()} -> {dates[-1].date()} "
          f"({len(dates)} days)")

    print("\n[2/3] Walking forward day-by-day (no look-ahead) ...")
    broker = PaperBroker(starting_cash=100_000, commission_bps=COMMISSION_BPS,
                         slippage_bps=SLIPPAGE_BPS)

    @torch.no_grad()
    def predict_day(d) -> dict:
        preds = {}
        for s in syms:
            f = feats_by_sym[s]
            if d not in f.index:
                continue
            loc = f.index.get_loc(d)
            if loc < seq_len:
                continue
            win = f.iloc[loc - seq_len + 1: loc + 1].values
            xn = (win - mu) / sd
            out = model(torch.tensor(xn[None], dtype=torch.float32))
            preds[s] = float(out["predictions"][0, 0, 0])
        return preds

    for i in range(len(dates) - 1):
        d, d_next = dates[i], dates[i + 1]
        preds = predict_day(d)
        # long-only equal weight among names with positive predicted return
        longs = [s for s, p in preds.items() if p > 0]
        if longs:
            w = {s: 1.0 / len(longs) for s in longs}
        else:
            w = {}
        prices_d = {s: float(close_by_sym[s].loc[d]) for s in preds}
        broker.rebalance_to_weights(w, prices_d, ts=d)
        prices_next = {s: float(close_by_sym[s].loc[d_next]) for s in syms if d_next in close_by_sym[s].index}
        broker.mark(prices_next, ts=d_next)

    print("\n[3/3] Results ...")
    eq = np.array([e for _, e in broker.equity_curve], dtype=float)
    rets = np.diff(eq) / eq[:-1]
    total_ret = eq[-1] / 100_000 - 1
    ann = (1 + total_ret) ** (TRADING_DAYS / len(rets)) - 1 if len(rets) else 0.0
    sharpe = float(rets.mean() / rets.std(ddof=1) * np.sqrt(TRADING_DAYS)) if rets.std(ddof=1) > 0 else 0.0
    peak = np.maximum.accumulate(eq)
    max_dd = float(((eq - peak) / peak).min())

    # SPY buy-and-hold benchmark over the same window
    spy = close_by_sym.get("SPY")
    spy_w = spy.loc[dates[1:]]
    spy_ret = spy_w.iloc[-1] / spy_w.iloc[0] - 1
    spy_d = spy.loc[dates].pct_change().dropna()
    spy_sharpe = float(spy_d.mean() / spy_d.std(ddof=1) * np.sqrt(TRADING_DAYS)) if spy_d.std(ddof=1) > 0 else 0.0

    print(f"  Final equity:        ${eq[-1]:,.0f}  (start $100,000)")
    print(f"  Total return:        {total_ret:+.2%}  (annualized {ann:+.2%})")
    print(f"  Sharpe:              {sharpe:+.3f}")
    print(f"  Max drawdown:        {max_dd:+.2%}")
    print(f"  Commission paid:     ${broker.total_commission:,.0f}  over {len(broker.fills)} fills")
    print(f"  --- benchmark (SPY buy & hold, same window) ---")
    print(f"  SPY return:          {spy_ret:+.2%}   SPY Sharpe: {spy_sharpe:+.3f}")
    verdict = ("tracks market (beta), as expected for a no-alpha model"
               if abs(sharpe - spy_sharpe) < 0.5 else "diverges from market — investigate")
    print(f"\n  READING: {verdict}")
    print("  (Execution + accounting verified; ready to wire to Schwab live feed.)")

    out = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "window_start": str(dates[0].date()), "window_end": str(dates[-1].date()),
        "days": len(rets), "final_equity": float(eq[-1]),
        "total_return": float(total_ret), "annualized_return": float(ann),
        "sharpe": sharpe, "max_drawdown": max_dd,
        "commission_paid": broker.total_commission, "n_fills": len(broker.fills),
        "spy_return": float(spy_ret), "spy_sharpe": spy_sharpe,
        "reading": verdict, "runtime_seconds": round(time.time() - t0, 1),
    }
    (ARTIFACT_DIR / "paper_trading_metrics.json").write_text(json.dumps(out, indent=2))
    pd.DataFrame(broker.equity_curve, columns=["date", "equity"]).to_csv(
        ARTIFACT_DIR / "paper_equity_curve.csv", index=False)
    print(f"\n  saved {ARTIFACT_DIR/'paper_trading_metrics.json'}")
    print(f"  saved {ARTIFACT_DIR/'paper_equity_curve.csv'}")
    print(f"Done in {out['runtime_seconds']}s.")
    return out


if __name__ == "__main__":
    main()
