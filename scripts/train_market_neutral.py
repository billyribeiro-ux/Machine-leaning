#!/usr/bin/env python3
"""
Market-neutral cross-sectional alpha test — honest, evidence-based.

The previous experiment (next-day direction, long-only) found only market BETA.
This isolates ALPHA by construction:

  * Large universe (~120 S&P 500 names), real FMP daily data.
  * Features ranked CROSS-SECTIONALLY within each day (so the model learns
    relative attractiveness, not market level).
  * Gradient-boosted trees (XGBoost) — the institutional standard for
    cross-sectional equity prediction.
  * Expanding-window WALK-FORWARD (always predict the future from the past).
  * Each OOS day: long the top quintile, short the bottom quintile,
    DOLLAR-NEUTRAL → market beta cancels. Returns are net of turnover cost.
  * Report cross-sectional IC + ICIR, long-short Sharpe, Deflated Sharpe,
    PBO, AND the portfolio's beta to the market (must be ~0 to be neutral).

Nothing is invented. If there is no alpha, the report says so.

Usage:
    SCANIFY_FMP_API_KEY=... python scripts/train_market_neutral.py
"""
from __future__ import annotations

import json, os, sys, time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.scanify.fmp_adapter import FMPAdapter  # noqa: E402
from src.ml.data_pipeline import FeatureEngineer, FeatureConfig  # noqa: E402
from src.backtest.validation import deflated_sharpe_ratio, probability_of_overfitting  # noqa: E402
import xgboost as xgb  # noqa: E402

# --------------------------------------------------------------------------- #
N_UNIVERSE = 120          # number of names to pull (FMP free-tier friendly)
MIN_BARS = 900
HORIZON = 1               # next-day forward return
N_FOLDS = 5               # expanding-window walk-forward blocks
QUANTILE = 0.2            # long top 20% / short bottom 20%
TXN_COST_BPS = 2.0        # per-side cost on turnover
TRADING_DAYS = 252
EMBARGO_DAYS = 5          # gap between train and test to kill leakage
SEED = 42
ARTIFACT_DIR = ROOT / "artifacts"
ARTIFACT_DIR.mkdir(exist_ok=True)
np.random.seed(SEED)


def build_panel():
    a = FMPAdapter()
    cons = a.get_index_constituents("sp500")
    syms = [c["symbol"] for c in cons if isinstance(c, dict) and c.get("symbol")]
    syms = sorted(set(syms))[:N_UNIVERSE]

    cfg = FeatureConfig(
        sequence_length=1, prediction_horizon=HORIZON,
        use_iv=False, use_greeks=False, use_put_call_ratio=False,
        use_options_volume=False, use_bid_ask_spread=False,
        use_trade_imbalance=False, use_order_flow=False, normalize_features=False,
    )
    fe = FeatureEngineer(cfg)

    frames, used = [], []
    for sym in syms:
        bars = a.get_historical_daily(sym, limit=4000)
        if not bars or len(bars) < MIN_BARS:
            continue
        df = pd.DataFrame(bars)
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").set_index("date")
        ohlcv = df[["open", "high", "low", "close", "volume"]].astype(float)
        feats = fe.generate_all_features(ohlcv).replace([np.inf, -np.inf], np.nan)
        close = ohlcv["close"].astype(float)
        fwd = close.shift(-HORIZON) / close - 1.0           # strictly future
        panel = feats.copy()
        panel["__fwd__"] = fwd.values
        panel["__sym__"] = sym
        panel["__date__"] = feats.index
        frames.append(panel.dropna(subset=["__fwd__"]))
        used.append(sym)

    data = pd.concat(frames, ignore_index=True)
    feat_cols = [c for c in data.columns if not c.startswith("__")]
    data = data.dropna(subset=feat_cols, how="any").reset_index(drop=True)
    return data, feat_cols, used


def cross_sectional_rank(df, cols):
    """Rank each feature within each day to [-0.5, 0.5] (market-neutral inputs)."""
    out = df.copy()
    g = out.groupby("__date__")
    for c in cols:
        out[c] = g[c].rank(pct=True) - 0.5
    return out


def walk_forward_dates(dates, n_folds, embargo):
    """Expanding-window splits over sorted unique dates."""
    uniq = np.array(sorted(dates.unique()))
    n = len(uniq)
    block = n // (n_folds + 1)
    splits = []
    for k in range(1, n_folds + 1):
        tr_end = block * k
        te_start = tr_end + embargo
        te_end = min(block * (k + 1), n)
        if te_start >= te_end:
            continue
        splits.append((set(uniq[:tr_end]), set(uniq[te_start:te_end])))
    return splits


def long_short_daily(day_df):
    """Dollar-neutral long-short return for one OOS day (gross, pre-cost)."""
    d = day_df.sort_values("pred")
    n = len(d)
    k = max(1, int(n * QUANTILE))
    short = d.iloc[:k]["__fwd__"].mean()
    longs = d.iloc[-k:]["__fwd__"].mean()
    # equal capital each side, dollar-neutral
    return 0.5 * longs - 0.5 * short, set(d.iloc[-k:]["__sym__"]), set(d.iloc[:k]["__sym__"])


def sharpe(r):
    r = np.asarray(r)
    return float(r.mean() / r.std(ddof=1) * np.sqrt(TRADING_DAYS)) if r.std(ddof=1) > 0 and len(r) > 1 else 0.0


def main():
    t0 = time.time()
    print("=" * 72)
    print("  MARKET-NEUTRAL CROSS-SECTIONAL ALPHA TEST (real FMP data)")
    print("=" * 72)
    if not os.environ.get("SCANIFY_FMP_API_KEY"):
        print("ERROR: set SCANIFY_FMP_API_KEY"); sys.exit(1)

    print(f"\n[1/4] Building panel ({N_UNIVERSE} S&P 500 names) ...")
    data, feat_cols, used = build_panel()
    print(f"  panel rows: {len(data):,}  | names: {len(used)}  | features: {len(feat_cols)}")
    print(f"  date span: {data['__date__'].min().date()} -> {data['__date__'].max().date()}")

    print("\n[2/4] Cross-sectional rank-normalising features per day ...")
    data = cross_sectional_rank(data, feat_cols)
    # cross-sectional target: rank of forward return within the day (alpha target)
    data["__y__"] = data.groupby("__date__")["__fwd__"].rank(pct=True) - 0.5

    print(f"\n[3/4] Walk-forward ({N_FOLDS} expanding folds, XGBoost) ...")
    splits = walk_forward_dates(data["__date__"], N_FOLDS, EMBARGO_DAYS)
    daily_ls, daily_dates = [], []
    fold_is_daily, fold_oos_daily = [], []
    ics = []
    prev_long, prev_short = set(), set()

    for fi, (tr_dates, te_dates) in enumerate(splits):
        tr = data[data["__date__"].isin(tr_dates)]
        te = data[data["__date__"].isin(te_dates)]
        model = xgb.XGBRegressor(
            n_estimators=300, max_depth=4, learning_rate=0.03,
            subsample=0.8, colsample_bytree=0.6, min_child_weight=20,
            reg_lambda=2.0, n_jobs=-1, random_state=SEED,
        )
        model.fit(tr[feat_cols].values, tr["__y__"].values)
        te = te.assign(pred=model.predict(te[feat_cols].values))
        tr_pred = tr.assign(pred=model.predict(tr[feat_cols].values))

        # daily cross-sectional IC (Spearman of pred vs actual fwd return)
        for dt, g in te.groupby("__date__"):
            if len(g) < 10:
                continue
            ic = g["pred"].corr(g["__fwd__"], method="spearman")
            if pd.notna(ic):
                ics.append(ic)
            ls, longs, shorts = long_short_daily(g)
            turnover = (len(longs ^ prev_long) + len(shorts ^ prev_short)) / max(1, 2 * len(longs))
            ls_net = ls - turnover * (TXN_COST_BPS / 1e4)
            daily_ls.append(ls_net); daily_dates.append(dt)
            prev_long, prev_short = longs, shorts
            fold_oos_daily.append(ls_net)

        # in-sample L/S for PBO
        for dt, g in tr_pred.groupby("__date__"):
            if len(g) < 10:
                continue
            ls, _, _ = long_short_daily(g)
            fold_is_daily.append(ls)

        oos_blk = [daily_ls[i] for i, d in enumerate(daily_dates) if d in te_dates]
        print(f"  fold {fi+1}/{len(splits)}: train_days={len(tr_dates)} test_days={len(te_dates)} "
              f"| block L/S Sharpe={sharpe(oos_blk):+.3f}")

    print("\n[4/4] Aggregate + neutrality + overfit diagnostics ...")
    ls = pd.Series(daily_ls, index=pd.to_datetime(daily_dates)).sort_index()
    ls = ls.groupby(ls.index).mean()                  # one number per calendar day
    ls_sharpe = sharpe(ls.values)
    mean_ic = float(np.mean(ics)); ic_std = float(np.std(ics, ddof=1))
    icir = float(mean_ic / ic_std * np.sqrt(TRADING_DAYS)) if ic_std > 0 else 0.0
    cum = float((1 + ls).prod() - 1)
    ann = float((1 + cum) ** (TRADING_DAYS / max(1, len(ls))) - 1)
    skew = float(ls.skew()); kurt = float(ls.kurt())
    dsr = deflated_sharpe_ratio(ls_sharpe, n_trials=1, n_observations=len(ls),
                                skewness=skew, kurtosis=kurt)

    # market beta of the L/S series (must be ~0 to be neutral)
    a = FMPAdapter()
    spy = a.get_historical_daily("SPY", limit=4000)
    spydf = pd.DataFrame(spy); spydf["date"] = pd.to_datetime(spydf["date"])
    spydf = spydf.sort_values("date").set_index("date")
    mkt = spydf["close"].astype(float).pct_change().reindex(ls.index).dropna()
    common = ls.index.intersection(mkt.index)
    beta = float(np.polyfit(mkt.loc[common].values, ls.loc[common].values, 1)[0]) if len(common) > 2 else float("nan")

    m = min(len(fold_is_daily), len(fold_oos_daily))
    pbo = probability_of_overfitting(
        np.array(fold_is_daily[:m]).reshape(1, -1).repeat(2, 0),
        np.array(fold_oos_daily[:m]).reshape(1, -1).repeat(2, 0),
    ) if m > 10 else float("nan")

    print(f"  OOS trading days:      {len(ls)}")
    print(f"  Cross-sectional IC:    {mean_ic:+.4f}  (daily mean; >0.02 = useful)")
    print(f"  ICIR (annualized):     {icir:+.3f}  (>0.5 = decent, >1 = strong)")
    print(f"  Long-short Sharpe:     {ls_sharpe:+.3f}  (net of {TXN_COST_BPS}bp costs)")
    print(f"  L/S cumulative:        {cum:+.2%}  (annualized {ann:+.2%})")
    print(f"  Market beta of L/S:    {beta:+.3f}  (~0 = truly market-neutral)")
    print(f"  Deflated Sharpe prob:  {dsr:.4f}")
    print(f"  Prob backtest overfit: {pbo:.4f}")

    edge = (mean_ic > 0.02 and icir > 0.5 and ls_sharpe > 0.5 and dsr > 0.90 and abs(beta) < 0.2)
    verdict = ("MEASURED MARKET-NEUTRAL ALPHA (passes IC/ICIR/Sharpe/DSR/neutrality gates)"
               if edge else "NO RELIABLE ALPHA DETECTED")
    print(f"\n  VERDICT: {verdict}")

    metrics = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "experiment": "market_neutral_cross_sectional_long_short",
        "universe_size": len(used), "panel_rows": int(len(data)),
        "n_features": len(feat_cols), "oos_days": int(len(ls)),
        "horizon": HORIZON, "quantile": QUANTILE, "txn_cost_bps": TXN_COST_BPS,
        "cross_sectional_ic": mean_ic, "icir": icir,
        "long_short_sharpe_net": ls_sharpe,
        "ls_cumulative_return": cum, "ls_annualized_return": ann,
        "market_beta": beta,
        "deflated_sharpe_probability": dsr,
        "probability_of_overfitting": pbo,
        "verdict": verdict, "runtime_seconds": round(time.time() - t0, 1),
    }
    (ARTIFACT_DIR / "market_neutral_metrics.json").write_text(json.dumps(metrics, indent=2))
    print(f"\n  saved {ARTIFACT_DIR/'market_neutral_metrics.json'}")
    print(f"Done in {metrics['runtime_seconds']}s.")
    return metrics


if __name__ == "__main__":
    main()
