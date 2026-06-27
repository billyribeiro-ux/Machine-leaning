# ML Validation Report — Honest, Evidence-Based

**Generated:** 2026-06-27 · **Pipeline:** `scripts/train_and_validate.py`
**Model:** Temporal Fusion Transformer (27k–80k params) · **Data:** real FMP `/stable` daily bars

---

## What was actually run (end-to-end, on real data)

1. Pulled **5 years of real daily OHLCV** (2021-08-09 → 2026-06-25) for 15 liquid names
   (SPY, QQQ, IWM, DIA, AAPL, MSFT, NVDA, AMZN, GOOGL, META, TSLA, JPM, XOM, JNJ, WMT) from FMP.
2. Built **115 features** per bar via the project's `FeatureEngineer` → **18,375 supervised sequences**
   (30-day windows → next-day return).
3. **Purged 5-fold cross-validation** (López de Prado) with per-fold z-score normalisation fit on
   **train only** (no look-ahead). Target is strictly the forward return.
4. Trained the **Temporal Fusion Transformer** per fold (12 epochs, CPU), evaluated **out-of-sample**.
5. Aggregated into an **equal-weight daily portfolio** (1,225 trading days), computed Sharpe net of
   1bp turnover cost, **Deflated Sharpe Ratio**, and **Probability of Backtest Overfitting**.

## Headline out-of-sample metrics

| Metric | Value | Reading |
|---|---|---|
| Directional accuracy | **51.4%** | ≈ coin flip (50%) |
| Information Coefficient (Spearman) | **+0.012** | ≈ 0 → negligible predictive skill |
| OOS Sharpe (net of costs) | **+0.966** | looks good — but see below |
| OOS annualized return | **+17.0%** | looks good — but see below |
| Deflated Sharpe probability | 1.000 | for a *single* config |
| Probability of backtest overfitting | 0.40 | moderate |
| Per-fold Sharpe | +1.56, +1.13, +2.10, **−0.69**, +1.93 | high dispersion / unstable |

## The decisive benchmark — is it skill or just market beta?

Equal-weight **buy-and-hold** of the *same 15 names* over the *same period*:

| | Sharpe | Annualized return |
|---|---|---|
| **Buy-and-hold (passive)** | **+0.948** | **+18.6%** |
| **TFT model (active, after costs)** | +0.966 | +17.0% |

The model's risk-adjusted return is **statistically indistinguishable from passively holding the
same stocks**, and its raw return is **lower** (17.0% vs 18.6%) after trading costs.

## Verdict

> **No reliable predictive edge.** The model's positive Sharpe is **market beta** — it was mostly
> long during a 2021–2026 bull market — **not alpha**. The near-zero IC (0.012), coin-flip
> directional accuracy (51.4%), a strongly negative fold (−0.69 Sharpe), and the buy-and-hold
> benchmark all converge on the same conclusion. The pipeline's own gate flagged
> **"NO RELIABLE EDGE DETECTED."**

This is a *good* outcome for honesty: the validation framework correctly refused to certify a
non-existent edge. Daily directional return prediction on liquid equities is one of the hardest
problems in finance; a small TFT on 115 generic technical features finding no edge is the expected,
truthful result — not a failure of the engineering.

## What would change the conclusion (future work)

- Predict a **harder-to-get-passively** target (cross-sectional rank, vol, or the 0DTE GEX signals
  this repo specializes in) rather than next-day direction.
- **Market-neutralize** (long-short, beta-hedged) so beta can't masquerade as alpha.
- Larger model + far more data (intraday, options) once Schwab OAuth is connected.
- Walk-forward with **honest `n_trials`** in the Deflated Sharpe (every architecture tried counts).

## Reproduce

```bash
SCANIFY_FMP_API_KEY=... python scripts/train_and_validate.py
```
Artifacts: `artifacts/tft_model.pt`, `artifacts/validation_metrics.json`, this report.
Tests: `pytest tests/ml/test_ml_core.py` (11 tests).
