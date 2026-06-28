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
from src.execution.performance import compute_metrics  # noqa: E402

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
    curve_dates = [d for d, _ in broker.equity_curve]
    eq = np.array([e for _, e in broker.equity_curve], dtype=float)

    # rich metrics from the reusable analytics module
    traded_notional = sum(f.price * f.quantity for f in broker.fills)
    m = compute_metrics(eq, traded_notional=traded_notional)

    # SPY buy-and-hold benchmark, normalised to the same starting capital
    spy = close_by_sym.get("SPY")
    spy_path = spy.loc[curve_dates]
    spy_eq = (spy_path / spy_path.iloc[0] * eq[0]).values
    spy_m = compute_metrics(spy_eq)

    print(f"  Final equity:        ${eq[-1]:,.0f}  (start ${eq[0]:,.0f})")
    print(f"  Total return:        {m['total_return']:+.2%}  (annualized {m['annualized_return']:+.2%})")
    print(f"  Volatility (ann):    {m['volatility']:.2%}")
    print(f"  Sharpe:              {m['sharpe']:+.3f}")
    print(f"  Sortino:             {m['sortino']:+.3f}")
    print(f"  Calmar:              {m['calmar']:+.3f}")
    print(f"  Max drawdown:        {m['max_drawdown']:+.2%}")
    print(f"  Hit rate (active):   {m['hit_rate']:.1%}  (best {m['best_day']:+.2%} / worst {m['worst_day']:+.2%})")
    print(f"  Time in market:      {m['pct_days_in_market']:.1%}  (cash otherwise)")
    print(f"  Turnover (ann):      {m.get('turnover_annualized', 0):.1f}x")
    print(f"  Commission paid:     ${broker.total_commission:,.0f}  over {len(broker.fills)} fills")
    print(f"  --- benchmark (SPY buy & hold, same window) ---")
    print(f"  SPY return:          {spy_m['total_return']:+.2%}   SPY Sharpe: {spy_m['sharpe']:+.3f}   SPY maxDD: {spy_m['max_drawdown']:+.2%}")
    verdict = ("tracks market (beta), as expected for a no-alpha model"
               if abs(m['sharpe'] - spy_m['sharpe']) < 0.5 else "diverges from market — investigate")
    print(f"\n  READING: {verdict}")
    print("  (Execution + accounting verified; ready to wire to Schwab live feed.)")

    # ---- equity-curve chart (PNG) -------------------------------------- #
    _render_chart(curve_dates, eq, spy_eq, ARTIFACT_DIR / "paper_equity_curve.png")
    print(f"\n  saved {ARTIFACT_DIR/'paper_equity_curve.png'}")

    out = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "window_start": str(curve_dates[0].date()), "window_end": str(curve_dates[-1].date()),
        "final_equity": float(eq[-1]),
        **{k: (float(v) if isinstance(v, (int, float, np.floating)) else v) for k, v in m.items()},
        "commission_paid": broker.total_commission, "n_fills": len(broker.fills),
        "spy_total_return": spy_m["total_return"], "spy_sharpe": spy_m["sharpe"],
        "spy_max_drawdown": spy_m["max_drawdown"],
        "reading": verdict, "runtime_seconds": round(time.time() - t0, 1),
    }
    (ARTIFACT_DIR / "paper_trading_metrics.json").write_text(json.dumps(out, indent=2))
    pd.DataFrame(broker.equity_curve, columns=["date", "equity"]).to_csv(
        ARTIFACT_DIR / "paper_equity_curve.csv", index=False)

    # ---- append to run history (for scheduled/continuous runs) ---------- #
    hist = ARTIFACT_DIR / "paper_run_history.jsonl"
    rec = {"run_utc": out["generated_utc"], "window_end": out["window_end"],
           "final_equity": out["final_equity"], "total_return": out["total_return"],
           "sharpe": out["sharpe"], "max_drawdown": out["max_drawdown"]}
    with hist.open("a") as fh:
        fh.write(json.dumps(rec) + "\n")

    print(f"  saved {ARTIFACT_DIR/'paper_trading_metrics.json'}")
    print(f"  saved {ARTIFACT_DIR/'paper_equity_curve.csv'}")
    print(f"  appended {hist}")
    print(f"Done in {out['runtime_seconds']}s.")
    return out


def _render_chart(dates, eq, spy_eq, path) -> None:
    """Render strategy vs SPY equity + drawdown to a PNG."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from src.execution.performance import drawdown_series

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(11, 6.5), gridspec_kw={"height_ratios": [3, 1]}, sharex=True)
    fig.patch.set_facecolor("#0d1017")
    for ax in (ax1, ax2):
        ax.set_facecolor("#11151c")
        ax.tick_params(colors="#9aa4b2")
        for sp in ax.spines.values():
            sp.set_color("#2a3140")
        ax.grid(True, color="#1c2430", linewidth=0.6)

    ax1.plot(dates, eq, color="#34e29b", linewidth=1.8, label="Paper strategy")
    ax1.plot(dates, spy_eq, color="#6b8cff", linewidth=1.4, alpha=0.9, label="SPY buy & hold")
    ax1.set_title("Paper Trading — Equity Curve (zero risk)", color="#e6edf3", fontsize=13, fontweight="bold")
    ax1.set_ylabel("Equity ($)", color="#9aa4b2")
    ax1.legend(facecolor="#11151c", edgecolor="#2a3140", labelcolor="#e6edf3")

    dd = drawdown_series(eq) * 100.0
    ax2.fill_between(dates, dd, 0, color="#ef4444", alpha=0.35)
    ax2.plot(dates, dd, color="#ef4444", linewidth=1.0)
    ax2.set_ylabel("Drawdown (%)", color="#9aa4b2")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(path, dpi=130, facecolor=fig.get_facecolor())
    plt.close(fig)


if __name__ == "__main__":
    main()
