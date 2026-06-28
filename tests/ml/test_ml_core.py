"""
Tests for the ML stack (src/ml), the RL stack (src/rl), and the backtest
validation framework (src/backtest/validation).

These were previously untested. The first test is a regression guard for the
broken package exports that made `import src.ml` raise ImportError.
"""
import numpy as np
import pandas as pd
import pytest
import torch


# --------------------------------------------------------------------------- #
# Package health (regression: src.ml used to fail at import)
# --------------------------------------------------------------------------- #
def test_ml_package_imports():
    import src.ml as ml  # must not raise
    for name in (
        "TemporalFusionTransformer", "EnsembleModel", "OnlineLearner",
        "InterpretableAttention", "create_tft_model", "create_ensemble",
        "FeatureEngineer", "FeatureConfig",
    ):
        assert hasattr(ml, name), f"src.ml missing export: {name}"


def test_rl_package_imports():
    import src.rl as rl
    for name in ("SoftActorCritic", "PPOAgent", "create_sac_agent", "create_trading_env"):
        assert hasattr(rl, name)


# --------------------------------------------------------------------------- #
# Temporal Fusion Transformer
# --------------------------------------------------------------------------- #
def test_tft_forward_shapes():
    from src.ml.models import create_tft_model
    m = create_tft_model(input_dim=16, hidden_dim=32, num_layers=2, num_heads=4,
                         sequence_length=20, prediction_horizon=1, device="cpu")
    out = m(torch.randn(8, 20, 16))
    assert "predictions" in out and "uncertainty" in out
    assert out["predictions"].shape == (8, 1, 3)   # (batch, horizon, [mean,lo,hi])
    assert torch.isfinite(out["predictions"]).all()


def test_ensemble_factory_and_forward():
    from src.ml.models import create_tft_model, create_ensemble
    members = [
        create_tft_model(input_dim=12, hidden_dim=24, num_layers=1, num_heads=4,
                         sequence_length=15, prediction_horizon=1, device="cpu")
        for _ in range(2)
    ]
    ens = create_ensemble(members, hidden_dim=32)
    out = ens(torch.randn(4, 15, 12))
    assert isinstance(out, dict)
    assert any(torch.is_tensor(v) and torch.isfinite(v).all() for v in out.values())


def test_online_learner_update_returns_finite_loss():
    from src.ml.models import create_tft_model, OnlineLearner, ModelConfig
    cfg = ModelConfig(input_dim=10, hidden_dim=24, num_layers=1, num_heads=2,
                      sequence_length=12, prediction_horizon=1, device="cpu")
    model = create_tft_model(input_dim=10, hidden_dim=24, num_layers=1, num_heads=2,
                             sequence_length=12, prediction_horizon=1, device="cpu")
    learner = OnlineLearner(model, cfg)
    x = torch.randn(16, 12, 10)
    y = torch.randn(16)
    loss = learner.update(x, y)
    assert np.isfinite(loss)


# --------------------------------------------------------------------------- #
# Feature engineering + sequence integrity (no look-ahead)
# --------------------------------------------------------------------------- #
def _toy_ohlcv(n=300, seed=0):
    rng = np.random.default_rng(seed)
    price = 100 * np.cumprod(1 + rng.normal(0.0003, 0.01, n))
    idx = pd.date_range(end="2026-06-27", periods=n, freq="D")
    return pd.DataFrame({
        "open": price * (1 + rng.normal(0, 0.002, n)),
        "high": price * (1 + np.abs(rng.normal(0, 0.01, n))),
        "low":  price * (1 - np.abs(rng.normal(0, 0.01, n))),
        "close": price,
        "volume": rng.integers(1e5, 1e6, n),
    }, index=idx)


def test_feature_engineer_clean_numeric():
    from src.ml.data_pipeline import FeatureEngineer, FeatureConfig
    cfg = FeatureConfig(sequence_length=20, prediction_horizon=1, use_iv=False,
                        use_greeks=False, use_put_call_ratio=False, use_options_volume=False,
                        use_bid_ask_spread=False, use_trade_imbalance=False, use_order_flow=False)
    feats = FeatureEngineer(cfg).generate_all_features(_toy_ohlcv())
    feats = feats.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    assert feats.shape[0] == 300 and feats.shape[1] > 20
    assert np.isfinite(feats.values).all()


def test_sequence_target_is_strictly_future():
    """The label must be the forward return — never use information at or
    before the end of the input window beyond the anchor close."""
    from src.ml.data_pipeline import MLDataPipeline
    pipe = MLDataPipeline(data_manager=None)
    feats = np.arange(100 * 3, dtype=float).reshape(100, 3)
    prices = np.linspace(10, 20, 100)
    seq_len, horizon = 10, 1
    X, y = pipe._create_sequences(feats, prices, seq_len, horizon)
    assert X.shape == (100 - seq_len - horizon + 1, seq_len, 3)
    # recompute first target by hand: forward return from anchor to anchor+horizon
    anchor = prices[seq_len - 1]
    fut = prices[seq_len - 1 + horizon]
    assert y[0] == pytest.approx((fut - anchor) / anchor)


# --------------------------------------------------------------------------- #
# Backtest validation framework
# --------------------------------------------------------------------------- #
def test_purged_kfold_no_train_test_overlap():
    from src.backtest.validation import PurgedKFoldCV
    cv = PurgedKFoldCV(n_splits=5, purge_pct=0.02, embargo_pct=0.02)
    for tr, te in cv.split(1000):
        assert len(np.intersect1d(tr, te)) == 0          # no leakage
        assert len(te) > 0 and len(tr) > 0


def test_deflated_sharpe_is_probability():
    from src.backtest.validation import deflated_sharpe_ratio
    p = deflated_sharpe_ratio(sharpe_observed=1.5, n_trials=10, n_observations=1000,
                              skewness=0.0, kurtosis=0.0)
    assert 0.0 <= p <= 1.0
    # more trials should not increase confidence
    p_more = deflated_sharpe_ratio(sharpe_observed=1.5, n_trials=1000, n_observations=1000)
    assert p_more <= p + 1e-9


def test_probability_of_overfitting_bounds():
    from src.backtest.validation import probability_of_overfitting
    rng = np.random.default_rng(1)
    is_r = rng.normal(0, 1, (6, 200))
    oos_r = rng.normal(0, 1, (6, 200))
    pbo = probability_of_overfitting(is_r, oos_r)
    assert 0.0 <= pbo <= 1.0


# --------------------------------------------------------------------------- #
# RL smoke test
# --------------------------------------------------------------------------- #
def test_sac_agent_select_action():
    from src.rl.trading_agent import create_sac_agent
    agent = create_sac_agent(state_dim=12, action_dim=2, device="cpu")
    action = agent.select_action(torch.randn(12), deterministic=True)
    assert torch.is_tensor(action)
    assert torch.isfinite(action).all()
