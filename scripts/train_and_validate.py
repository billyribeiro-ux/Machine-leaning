#!/usr/bin/env python3
"""
End-to-end ML training + honest validation on REAL market data.

Pipeline:
  1. Pull multi-year daily OHLCV from FMP (/stable) for a basket of symbols.
  2. Build features via the project's FeatureEngineer.
  3. Build supervised sequences (X = feature window, y = next-day return).
  4. Purged K-Fold CV (López de Prado) — no look-ahead, per-fold z-score
     normalisation fit on TRAIN only.
  5. Train a Temporal Fusion Transformer per fold; evaluate OUT-OF-SAMPLE.
  6. Report directional accuracy, Information Coefficient, and a cost-aware
     long/short Sharpe — plus Deflated Sharpe Ratio and Probability of
     Backtest Overfitting.
  7. Persist a model artifact, a metrics JSON, and a human-readable report.

Everything reported is measured. No numbers are invented. If there is no
edge, the report will say so.

Usage:
    SCANIFY_FMP_API_KEY=... python scripts/train_and_validate.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.scanify.fmp_adapter import FMPAdapter  # noqa: E402
from src.ml.data_pipeline import FeatureEngineer, FeatureConfig  # noqa: E402
from src.ml.models import create_tft_model, ModelConfig  # noqa: E402
from src.backtest.validation import (  # noqa: E402
    PurgedKFoldCV,
    deflated_sharpe_ratio,
    probability_of_overfitting,
)

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
SYMBOLS = [
    "SPY", "QQQ", "IWM", "DIA",            # broad index ETFs
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL",
    "META", "TSLA", "JPM", "XOM", "JNJ", "WMT",
]
SEQ_LEN = 30
HORIZON = 1                 # predict next-day return
N_SPLITS = 5
EPOCHS = 12
BATCH = 256
TXN_COST_BPS = 1.0         # per-side cost on turnover (1bp ≈ liquid ETF)
TRADING_DAYS = 252
SEED = 42

ARTIFACT_DIR = ROOT / "artifacts"
ARTIFACT_DIR.mkdir(exist_ok=True)

torch.manual_seed(SEED)
np.random.seed(SEED)
DEVICE = "cpu"


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #
def fetch_ohlcv(adapter: FMPAdapter, symbol: str) -> pd.DataFrame | None:
    bars = adapter.get_historical_daily(symbol, limit=4000)
    if not bars or len(bars) < 300:
        return None
    df = pd.DataFrame(bars)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").set_index("date")
    cols = ["open", "high", "low", "close", "volume"]
    return df[cols].astype(float)


def build_dataset():
    adapter = FMPAdapter()
    cfg = FeatureConfig(
        sequence_length=SEQ_LEN,
        prediction_horizon=HORIZON,
        # disable feature families that need data FMP daily bars don't carry
        use_iv=False, use_greeks=False, use_put_call_ratio=False,
        use_options_volume=False, use_bid_ask_spread=False,
        use_trade_imbalance=False, use_order_flow=False,
        normalize_features=False,  # we normalise per-fold to avoid leakage
    )
    fe = FeatureEngineer(cfg)

    X_parts, y_parts, t_parts, feat_names = [], [], [], None
    used = []
    for sym in SYMBOLS:
        ohlcv = fetch_ohlcv(adapter, sym)
        if ohlcv is None:
            print(f"  - {sym}: insufficient data, skipped")
            continue
        feats = fe.generate_all_features(ohlcv)
        feats = feats.replace([np.inf, -np.inf], np.nan).fillna(0.0)
        if feat_names is None:
            feat_names = list(feats.columns)
        fv = feats.values.astype(np.float32)
        close = ohlcv["close"].values.astype(np.float64)
        dates = ohlcv.index.values

        for i in range(len(fv) - SEQ_LEN - HORIZON + 1):
            X_parts.append(fv[i:i + SEQ_LEN])
            fut = (close[i + SEQ_LEN + HORIZON - 1] - close[i + SEQ_LEN - 1]) / close[i + SEQ_LEN - 1]
            y_parts.append(fut)
            t_parts.append(dates[i + SEQ_LEN - 1])
        used.append(sym)
        print(f"  - {sym}: {len(fv)} bars -> running total {len(X_parts)} sequences")

    X = np.asarray(X_parts, dtype=np.float32)
    y = np.asarray(y_parts, dtype=np.float32)
    t = np.asarray(t_parts)
    # chronological global order (purged CV assumes time-ordering)
    order = np.argsort(t)
    return X[order], y[order], t[order], feat_names, used


# --------------------------------------------------------------------------- #
# Model train / predict
# --------------------------------------------------------------------------- #
def train_fold(X_tr, y_tr, input_dim) -> nn.Module:
    model = create_tft_model(
        input_dim=input_dim, hidden_dim=64, num_layers=2, num_heads=4,
        sequence_length=SEQ_LEN, prediction_horizon=HORIZON, dropout=0.1,
        device=DEVICE,
    ).to(DEVICE)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-5)
    crit = nn.HuberLoss(delta=0.01)

    Xt = torch.tensor(X_tr, dtype=torch.float32)
    yt = torch.tensor(y_tr, dtype=torch.float32)
    n = len(Xt)
    model.train()
    for epoch in range(EPOCHS):
        perm = torch.randperm(n)
        tot = 0.0
        for s in range(0, n, BATCH):
            idx = perm[s:s + BATCH]
            xb, yb = Xt[idx].to(DEVICE), yt[idx].to(DEVICE)
            opt.zero_grad()
            out = model(xb)
            pred = out["predictions"][:, 0, 0]  # mean quantile, horizon 0
            loss = crit(pred, yb)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            tot += loss.item() * len(idx)
    return model


@torch.no_grad()
def predict(model, X) -> np.ndarray:
    model.eval()
    preds = []
    Xt = torch.tensor(X, dtype=torch.float32)
    for s in range(0, len(Xt), 1024):
        out = model(Xt[s:s + 1024].to(DEVICE))
        preds.append(out["predictions"][:, 0, 0].cpu().numpy())
    return np.concatenate(preds)


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #
def fold_metrics(pred, actual):
    # Directional accuracy (ignore flat actuals)
    nz = actual != 0
    dir_acc = float(np.mean(np.sign(pred[nz]) == np.sign(actual[nz]))) if nz.any() else float("nan")
    # Information coefficient (Spearman rank corr)
    pr = pd.Series(pred).rank().values
    ar = pd.Series(actual).rank().values
    ic = float(np.corrcoef(pr, ar)[0, 1]) if len(pred) > 2 else float("nan")
    # Cost-aware long/short strategy: position = sign(pred), unit gross
    pos = np.sign(pred)
    turnover = np.abs(np.diff(np.concatenate([[0.0], pos])))
    cost = turnover * (TXN_COST_BPS / 1e4)
    strat_ret = pos * actual - cost
    return dir_acc, ic, strat_ret


def sharpe(returns) -> float:
    r = np.asarray(returns)
    if r.std(ddof=1) == 0 or len(r) < 2:
        return 0.0
    return float(r.mean() / r.std(ddof=1) * np.sqrt(TRADING_DAYS))


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main():
    t0 = time.time()
    print("=" * 70)
    print("  ML TRAINING + HONEST VALIDATION  (real FMP data)")
    print("=" * 70)

    if not os.environ.get("SCANIFY_FMP_API_KEY"):
        print("ERROR: set SCANIFY_FMP_API_KEY"); sys.exit(1)

    print("\n[1/4] Building dataset from FMP /stable ...")
    X, y, t, feat_names, used = build_dataset()
    input_dim = X.shape[2]
    print(f"\nDataset: X={X.shape}  y={y.shape}  features={input_dim}")
    print(f"Symbols used ({len(used)}): {', '.join(used)}")
    print(f"Date span: {pd.Timestamp(t.min()).date()} -> {pd.Timestamp(t.max()).date()}")
    print(f"Target (next-{HORIZON}d return): mean={y.mean():+.5f} std={y.std():.5f}")

    print(f"\n[2/4] Purged {N_SPLITS}-fold CV training (TFT, {EPOCHS} epochs/fold, CPU) ...")
    cv = PurgedKFoldCV(n_splits=N_SPLITS, purge_pct=0.01, embargo_pct=0.01)
    splits = cv.split(len(X))

    # Collect per-sample OOS (date, position, actual) so we can build a
    # PORTFOLIO daily equity curve. Concatenating raw per-sample returns is
    # wrong: 15 symbols trade the SAME days, so they are concurrent positions,
    # not a sequential series. We equal-weight across symbols per calendar day.
    oos_dates, oos_pos, oos_actual = [], [], []
    fold_oos_ret_list = []        # per-fold daily portfolio returns (for PBO)
    fold_is_ret_list = []
    dir_accs, ics, fold_sharpes = [], [], []

    def daily_portfolio(dates, pos, actual):
        """Equal-weight daily portfolio return, net of turnover costs."""
        df = pd.DataFrame({"date": pd.to_datetime(dates), "pos": pos, "act": actual})
        # cost per name on position change vs its own previous appearance
        df = df.sort_values("date")
        gross = df.assign(r=df["pos"] * df["act"])
        daily = gross.groupby("date")["r"].mean()
        # approximate turnover cost: mean |pos| change day-over-day * cost
        daily_pos = df.groupby("date")["pos"].mean()
        turn = daily_pos.diff().abs().fillna(daily_pos.abs())
        daily_net = daily - turn * (TXN_COST_BPS / 1e4)
        return daily_net

    for fi, (tr, te) in enumerate(splits):
        mu = X[tr].reshape(-1, input_dim).mean(0)
        sd = X[tr].reshape(-1, input_dim).std(0) + 1e-8
        Xtr = (X[tr] - mu) / sd
        Xte = (X[te] - mu) / sd

        model = train_fold(Xtr, y[tr], input_dim)
        p_te = predict(model, Xte)
        p_tr = predict(model, Xtr)

        da, ic, _ = fold_metrics(p_te, y[te])
        dir_accs.append(da); ics.append(ic)

        # per-fold portfolio daily series (OOS and IS) for honest Sharpe/PBO
        oos_daily = daily_portfolio(t[te], np.sign(p_te), y[te])
        is_daily = daily_portfolio(t[tr], np.sign(p_tr), y[tr])
        fold_sharpes.append(sharpe(oos_daily.values))
        fold_oos_ret_list.append(oos_daily.values)
        fold_is_ret_list.append(is_daily.values)

        oos_dates.append(t[te]); oos_pos.append(np.sign(p_te)); oos_actual.append(y[te])
        print(f"  fold {fi+1}/{N_SPLITS}: train={len(tr)} test={len(te)} "
              f"| dirAcc={da:.4f} IC={ic:+.4f} OOS_Sharpe={fold_sharpes[-1]:+.3f}")

    print("\n[3/4] Aggregate out-of-sample metrics (portfolio daily series) ...")
    port = daily_portfolio(
        np.concatenate(oos_dates), np.concatenate(oos_pos), np.concatenate(oos_actual)
    )
    oos = port.values
    oos_sharpe = sharpe(oos)
    n_days = int(len(oos))                 # independent-ish daily observations
    mean_da = float(np.nanmean(dir_accs))
    mean_ic = float(np.nanmean(ics))
    skew = float(pd.Series(oos).skew())
    kurt = float(pd.Series(oos).kurt())

    n_trials = 1                            # we honestly tried one config
    dsr = deflated_sharpe_ratio(
        sharpe_observed=oos_sharpe, n_trials=max(1, n_trials),
        n_observations=n_days, skewness=skew, kurtosis=kurt,
    )

    m = min(len(r) for r in fold_is_ret_list)
    is_mat = np.vstack([r[:m] for r in fold_is_ret_list])
    oos_mat = np.vstack([r[:m] for r in fold_oos_ret_list])
    pbo = probability_of_overfitting(is_mat, oos_mat)

    cum = float(np.prod(1 + oos) - 1)       # legit: one equal-weight daily curve
    ann = float((1 + cum) ** (TRADING_DAYS / max(1, n_days)) - 1)
    print(f"  OOS portfolio days:   {n_days}  (equal-weight across symbols)")
    print(f"  Mean directional acc: {mean_da:.4f}  (0.50 = coin flip)")
    print(f"  Mean IC (Spearman):   {mean_ic:+.4f}  (0.00 = no skill)")
    print(f"  OOS Sharpe (net):     {oos_sharpe:+.3f}")
    print(f"  OOS cumulative ret:   {cum:+.2%}  (annualized {ann:+.2%})")
    print(f"  Deflated Sharpe prob: {dsr:.4f}  (P[true Sharpe>0]; >0.95 = strong)")
    print(f"  Prob backtest overfit:{pbo:.4f}  (0 = robust, 1 = overfit)")

    # ---- verdict --------------------------------------------------------- #
    edge = (mean_ic > 0.02 and oos_sharpe > 0.3 and dsr > 0.90 and pbo < 0.5)
    verdict = (
        "MEASURED EDGE (passes IC/Sharpe/DSR/PBO gates)" if edge
        else "NO RELIABLE EDGE DETECTED on this data/config"
    )
    print(f"\n  VERDICT: {verdict}")

    print("\n[4/4] Persisting artifacts ...")
    # Final model trained on ALL data (normalised globally) for deployment.
    mu = X.reshape(-1, input_dim).mean(0); sd = X.reshape(-1, input_dim).std(0) + 1e-8
    final = train_fold((X - mu) / sd, y, input_dim)
    torch.save(
        {
            "state_dict": final.state_dict(),
            "feature_names": feat_names,
            "norm_mean": mu, "norm_std": sd,
            "seq_len": SEQ_LEN, "horizon": HORIZON, "input_dim": input_dim,
        },
        ARTIFACT_DIR / "tft_model.pt",
    )
    metrics = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "symbols": used, "n_sequences": int(len(X)), "n_features": int(input_dim),
        "date_start": str(pd.Timestamp(t.min()).date()),
        "date_end": str(pd.Timestamp(t.max()).date()),
        "seq_len": SEQ_LEN, "horizon": HORIZON, "n_splits": N_SPLITS,
        "epochs_per_fold": EPOCHS, "txn_cost_bps": TXN_COST_BPS,
        "oos_portfolio_days": n_days,
        "mean_directional_accuracy": mean_da,
        "mean_information_coefficient": mean_ic,
        "oos_sharpe_net": oos_sharpe,
        "oos_cumulative_return": cum,
        "oos_annualized_return": ann,
        "fold_sharpes": fold_sharpes,
        "deflated_sharpe_probability": dsr,
        "probability_of_overfitting": pbo,
        "oos_return_skew": skew, "oos_return_excess_kurtosis": kurt,
        "verdict": verdict,
        "runtime_seconds": round(time.time() - t0, 1),
    }
    (ARTIFACT_DIR / "validation_metrics.json").write_text(json.dumps(metrics, indent=2))
    print(f"  saved {ARTIFACT_DIR/'tft_model.pt'}")
    print(f"  saved {ARTIFACT_DIR/'validation_metrics.json'}")
    print(f"\nDone in {metrics['runtime_seconds']}s.")
    return metrics


if __name__ == "__main__":
    main()
