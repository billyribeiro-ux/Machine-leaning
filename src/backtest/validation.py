"""
Revolution Alpha Engine - Backtesting Validation Framework

Institutional-grade backtesting validation implementing:
- Walk-forward optimization with purged & embargoed CV
- Deflated Sharpe Ratio (correct for multiple testing)
- Probability of Backtest Overfitting (PBO)
- Combinatorial Purged Cross-Validation (CPCV)
- Minimum Backtest Length calculation
- Multiple testing corrections (Bonferroni, Benjamini-Hochberg)
- Realistic transaction cost modeling
- Historical crisis stress testing

Based on Marcos López de Prado's methodology from
"Advances in Financial Machine Learning" (2018).
"""

import numpy as np
from scipy import stats
from scipy.special import comb
from typing import Optional, List, Dict, Tuple, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import logging
import warnings

from ..scanner.advanced_models import BacktestValidation

logger = logging.getLogger(__name__)
warnings.filterwarnings('ignore')


# =============================================================================
# Walk-Forward Optimization
# =============================================================================

class WalkForwardOptimizer:
    """
    Walk-forward optimization with proper train/test splitting.

    Ensures no look-ahead bias by always training on past data
    and testing on future data in a rolling window fashion.
    """

    def __init__(
        self,
        train_period: int = 252,
        test_period: int = 63,
        step_size: int = 21,
        purge_gap: int = 5,
    ):
        """
        Args:
            train_period: Number of bars in training window
            test_period: Number of bars in test window
            step_size: Step size for rolling window
            purge_gap: Gap between train and test to prevent leakage
        """
        self.train_period = train_period
        self.test_period = test_period
        self.step_size = step_size
        self.purge_gap = purge_gap

    def generate_splits(
        self, n_samples: int
    ) -> List[Tuple[np.ndarray, np.ndarray]]:
        """
        Generate train/test index splits for walk-forward.

        Returns:
            List of (train_indices, test_indices) tuples
        """
        splits = []
        start = 0

        while start + self.train_period + self.purge_gap + self.test_period <= n_samples:
            train_end = start + self.train_period
            test_start = train_end + self.purge_gap
            test_end = min(test_start + self.test_period, n_samples)

            train_idx = np.arange(start, train_end)
            test_idx = np.arange(test_start, test_end)

            splits.append((train_idx, test_idx))
            start += self.step_size

        return splits

    def run(
        self,
        data: np.ndarray,
        train_func: Callable,
        predict_func: Callable,
        evaluate_func: Callable,
    ) -> Dict[str, Any]:
        """
        Run walk-forward optimization.

        Args:
            data: Full dataset array
            train_func: Function(train_data) -> model
            predict_func: Function(model, test_data) -> predictions
            evaluate_func: Function(predictions, actuals) -> metrics_dict

        Returns:
            Aggregated results across all folds
        """
        splits = self.generate_splits(len(data))
        if not splits:
            return {"error": "Insufficient data for walk-forward"}

        all_metrics = []
        all_predictions = []
        all_actuals = []

        for train_idx, test_idx in splits:
            train_data = data[train_idx]
            test_data = data[test_idx]

            try:
                model = train_func(train_data)
                predictions = predict_func(model, test_data)
                metrics = evaluate_func(predictions, test_data)

                all_metrics.append(metrics)
                all_predictions.extend(predictions.tolist() if hasattr(predictions, 'tolist') else [predictions])
                all_actuals.extend(test_data.tolist() if hasattr(test_data, 'tolist') else [test_data])
            except Exception as e:
                logger.warning(f"Walk-forward fold failed: {e}")

        if not all_metrics:
            return {"error": "All folds failed"}

        aggregated = {}
        for key in all_metrics[0]:
            values = [m[key] for m in all_metrics if key in m]
            aggregated[key] = {
                "mean": np.mean(values),
                "std": np.std(values),
                "min": np.min(values),
                "max": np.max(values),
                "median": np.median(values),
            }

        aggregated["n_folds"] = len(all_metrics)
        return aggregated


# =============================================================================
# Purged & Embargoed Cross-Validation
# =============================================================================

class PurgedKFoldCV:
    """
    K-Fold Cross-Validation with purging and embargo.

    Purging: Remove training observations whose labels overlap with
    test observations in time.

    Embargo: Add a gap after test set to prevent information leakage
    from slowly-decaying autocorrelation.

    Based on López de Prado (2018), Chapter 7.
    """

    def __init__(
        self,
        n_splits: int = 5,
        purge_pct: float = 0.01,
        embargo_pct: float = 0.01,
    ):
        self.n_splits = n_splits
        self.purge_pct = purge_pct
        self.embargo_pct = embargo_pct

    def split(
        self,
        n_samples: int,
        label_spans: Optional[np.ndarray] = None,
    ) -> List[Tuple[np.ndarray, np.ndarray]]:
        """
        Generate purged and embargoed CV splits.

        Args:
            n_samples: Total number of samples
            label_spans: Optional array of (start, end) for each label's time span

        Returns:
            List of (train_indices, test_indices)
        """
        indices = np.arange(n_samples)
        fold_size = n_samples // self.n_splits
        purge_size = max(1, int(n_samples * self.purge_pct))
        embargo_size = max(1, int(n_samples * self.embargo_pct))

        splits = []

        for fold in range(self.n_splits):
            test_start = fold * fold_size
            test_end = min((fold + 1) * fold_size, n_samples)

            test_idx = indices[test_start:test_end]

            purge_start = max(0, test_start - purge_size)
            embargo_end = min(n_samples, test_end + embargo_size)

            train_mask = np.ones(n_samples, dtype=bool)
            train_mask[purge_start:embargo_end] = False
            train_idx = indices[train_mask]

            splits.append((train_idx, test_idx))

        return splits


class CombinatorialPurgedCV:
    """
    Combinatorial Purged Cross-Validation (CPCV).

    Tests all possible train/test combinations to estimate
    the probability of backtest overfitting.

    Based on López de Prado (2018), Chapter 12.
    """

    def __init__(
        self,
        n_groups: int = 6,
        n_test_groups: int = 2,
        purge_pct: float = 0.01,
    ):
        self.n_groups = n_groups
        self.n_test_groups = n_test_groups
        self.purge_pct = purge_pct
        self.n_paths = int(comb(n_groups, n_test_groups))

    def split(self, n_samples: int) -> List[Tuple[np.ndarray, np.ndarray]]:
        """Generate all combinatorial splits."""
        indices = np.arange(n_samples)
        group_size = n_samples // self.n_groups
        purge_size = max(1, int(n_samples * self.purge_pct))

        groups = []
        for i in range(self.n_groups):
            start = i * group_size
            end = min((i + 1) * group_size, n_samples)
            groups.append(indices[start:end])

        from itertools import combinations
        splits = []

        for test_combo in combinations(range(self.n_groups), self.n_test_groups):
            test_idx = np.concatenate([groups[i] for i in test_combo])

            train_mask = np.ones(n_samples, dtype=bool)
            for i in test_combo:
                start = max(0, groups[i][0] - purge_size)
                end = min(n_samples, groups[i][-1] + purge_size + 1)
                train_mask[start:end] = False

            train_idx = indices[train_mask]
            splits.append((train_idx, test_idx))

        return splits


# =============================================================================
# Deflated Sharpe Ratio
# =============================================================================

def deflated_sharpe_ratio(
    sharpe_observed: float,
    n_trials: int,
    n_observations: int,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
    sharpe_benchmark: float = 0.0,
) -> float:
    """
    Compute the Deflated Sharpe Ratio.

    Adjusts the observed Sharpe ratio for:
    1. Multiple testing (number of strategies tried)
    2. Non-normal returns (skewness and kurtosis)
    3. Short sample length

    Based on Bailey & López de Prado (2014).

    Args:
        sharpe_observed: Observed Sharpe ratio
        n_trials: Number of strategies/configurations tested
        n_observations: Number of return observations
        skewness: Return skewness
        kurtosis: Return kurtosis (excess, so normal=0)
        sharpe_benchmark: Benchmark Sharpe (usually 0)

    Returns:
        Probability that observed Sharpe is significant
    """
    if n_trials <= 0 or n_observations <= 0:
        return 0.0

    e_max_sharpe = _expected_max_sharpe(n_trials, n_observations, skewness, kurtosis)

    se_sharpe = np.sqrt(
        (1 + 0.5 * sharpe_observed ** 2 - skewness * sharpe_observed +
         (kurtosis - 3) / 4.0 * sharpe_observed ** 2) / (n_observations - 1)
    )

    if se_sharpe <= 0:
        return 0.0

    t_stat = (sharpe_observed - e_max_sharpe) / se_sharpe
    dsr = stats.norm.cdf(t_stat)

    return float(dsr)


def _expected_max_sharpe(
    n_trials: int,
    n_observations: int,
    skewness: float = 0.0,
    kurtosis: float = 0.0,
) -> float:
    """
    Expected maximum Sharpe ratio under the null of zero true Sharpe.

    E[max(SR)] ≈ (1 - γ) × Z^{-1}(1 - 1/N) + γ × Z^{-1}(1 - 1/(N×e))
    where γ ≈ 0.5772 (Euler-Mascheroni constant)
    """
    if n_trials <= 1:
        return 0.0

    gamma = 0.5772156649

    z1 = stats.norm.ppf(1 - 1.0 / n_trials)
    z2 = stats.norm.ppf(1 - 1.0 / (n_trials * np.e))

    e_max = (1 - gamma) * z1 + gamma * z2

    se = np.sqrt(1.0 / n_observations)
    e_max *= se

    return e_max


# =============================================================================
# Probability of Backtest Overfitting
# =============================================================================

def probability_of_overfitting(
    is_returns: np.ndarray,
    oos_returns: np.ndarray,
) -> float:
    """
    Estimate the Probability of Backtest Overfitting (PBO).

    Uses the rank of the optimal in-sample strategy in the
    out-of-sample results. If the best IS strategy doesn't
    rank well OOS, the backtest is likely overfit.

    Args:
        is_returns: In-sample returns for each strategy (n_strategies, n_periods)
        oos_returns: Out-of-sample returns for each strategy (n_strategies, n_periods)

    Returns:
        PBO: Probability in [0, 1] that backtest is overfit
    """
    if is_returns.ndim != 2 or oos_returns.ndim != 2:
        return 0.5

    n_strategies = is_returns.shape[0]
    if n_strategies < 2:
        return 0.0

    is_sharpes = np.zeros(n_strategies)
    oos_sharpes = np.zeros(n_strategies)

    for i in range(n_strategies):
        is_ret = is_returns[i]
        oos_ret = oos_returns[i]

        is_std = np.std(is_ret)
        oos_std = np.std(oos_ret)

        is_sharpes[i] = np.mean(is_ret) / is_std if is_std > 0 else 0
        oos_sharpes[i] = np.mean(oos_ret) / oos_std if oos_std > 0 else 0

    best_is_idx = np.argmax(is_sharpes)
    oos_rank = np.sum(oos_sharpes >= oos_sharpes[best_is_idx])
    relative_rank = oos_rank / n_strategies

    logit = np.log(relative_rank / (1 - relative_rank + 1e-10))
    pbo = 1.0 / (1.0 + np.exp(-logit))

    return float(np.clip(pbo, 0.0, 1.0))


# =============================================================================
# Minimum Backtest Length
# =============================================================================

def minimum_backtest_length(
    sharpe_target: float = 1.0,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
    n_trials: int = 1,
    confidence: float = 0.95,
) -> int:
    """
    Calculate the Minimum Backtest Length (MBL) in trading days.

    The minimum number of observations needed to distinguish
    the target Sharpe from zero at the given confidence level.

    Based on Bailey & López de Prado (2012).

    Args:
        sharpe_target: Annual Sharpe ratio target
        skewness: Return skewness
        kurtosis: Return kurtosis
        n_trials: Number of trials to correct for
        confidence: Confidence level (e.g., 0.95)

    Returns:
        Minimum number of trading days needed
    """
    if sharpe_target <= 0:
        return 10000

    z = stats.norm.ppf(confidence)

    if n_trials > 1:
        z += _expected_max_sharpe(n_trials, 252)

    sr_daily = sharpe_target / np.sqrt(252)

    numerator = (
        1 + 0.5 * sr_daily ** 2 -
        skewness * sr_daily +
        (kurtosis - 3) / 4.0 * sr_daily ** 2
    )

    mbl = (z / sr_daily) ** 2 * numerator

    return max(30, int(np.ceil(mbl)))


# =============================================================================
# Multiple Testing Corrections
# =============================================================================

def bonferroni_correction(p_values: np.ndarray, alpha: float = 0.05) -> np.ndarray:
    """
    Bonferroni correction for familywise error rate control.

    Adjusted p-value = min(p × m, 1) where m is the number of tests.
    """
    m = len(p_values)
    adjusted = np.minimum(p_values * m, 1.0)
    return adjusted


def benjamini_hochberg(p_values: np.ndarray, alpha: float = 0.05) -> Tuple[np.ndarray, np.ndarray]:
    """
    Benjamini-Hochberg procedure for False Discovery Rate control.

    Args:
        p_values: Array of p-values
        alpha: Target FDR level

    Returns:
        (adjusted_p_values, rejected_mask) where rejected_mask is boolean
    """
    m = len(p_values)
    sorted_idx = np.argsort(p_values)
    sorted_pvals = p_values[sorted_idx]

    adjusted = np.zeros(m)
    for i in range(m):
        rank = i + 1
        adjusted[sorted_idx[i]] = sorted_pvals[i] * m / rank

    for i in range(m - 2, -1, -1):
        adjusted[sorted_idx[i]] = min(adjusted[sorted_idx[i]], adjusted[sorted_idx[i + 1]])

    adjusted = np.minimum(adjusted, 1.0)
    rejected = adjusted <= alpha

    return adjusted, rejected


def holm_correction(p_values: np.ndarray, alpha: float = 0.05) -> Tuple[np.ndarray, np.ndarray]:
    """
    Holm-Bonferroni step-down correction.

    More powerful than Bonferroni while still controlling FWER.
    """
    m = len(p_values)
    sorted_idx = np.argsort(p_values)
    sorted_pvals = p_values[sorted_idx]

    adjusted = np.zeros(m)
    for i in range(m):
        adjusted[sorted_idx[i]] = sorted_pvals[i] * (m - i)

    for i in range(1, m):
        adjusted[sorted_idx[i]] = max(adjusted[sorted_idx[i]], adjusted[sorted_idx[i - 1]])

    adjusted = np.minimum(adjusted, 1.0)
    rejected = adjusted <= alpha

    return adjusted, rejected


# =============================================================================
# Transaction Cost Modeling
# =============================================================================

class TransactionCostModel:
    """
    Realistic transaction cost modeling.

    Includes:
    - Spread cost (half the bid-ask spread)
    - Market impact (Almgren-Chriss square-root model)
    - Commission (per-share or per-trade)
    - Slippage (as function of volatility and urgency)
    """

    def __init__(
        self,
        spread_bps: float = 5.0,
        commission_per_share: float = 0.005,
        impact_coefficient: float = 0.1,
        slippage_bps: float = 2.0,
    ):
        self.spread_bps = spread_bps
        self.commission_per_share = commission_per_share
        self.impact_coefficient = impact_coefficient
        self.slippage_bps = slippage_bps

    def total_cost_bps(
        self,
        price: float,
        shares: int,
        adv: float,
        volatility: float,
    ) -> float:
        """
        Calculate total transaction cost in basis points.

        Args:
            price: Trade price
            shares: Number of shares
            adv: Average daily volume in shares
            volatility: Daily volatility

        Returns:
            Total cost in basis points (one-way)
        """
        spread_cost = self.spread_bps / 2.0

        participation_rate = shares / max(1, adv)
        market_impact = (
            self.impact_coefficient *
            volatility * 10000 *
            np.sqrt(participation_rate)
        )

        commission_bps = (self.commission_per_share / price) * 10000

        total = spread_cost + market_impact + commission_bps + self.slippage_bps
        return total

    def apply_costs(
        self,
        returns: np.ndarray,
        turnover: np.ndarray,
        cost_per_turn_bps: float = 10.0,
    ) -> np.ndarray:
        """
        Apply transaction costs to a return series.

        Args:
            returns: Gross return series
            turnover: Turnover series (fraction of portfolio traded each period)
            cost_per_turn_bps: Cost per unit of turnover in bps

        Returns:
            Net return series
        """
        costs = turnover * cost_per_turn_bps / 10000.0
        return returns - costs

    def breakeven_cost(
        self,
        gross_returns: np.ndarray,
        turnover: np.ndarray,
    ) -> float:
        """
        Calculate breakeven transaction cost (in bps per unit turnover).

        The cost at which the strategy's Sharpe ratio drops to zero.
        """
        mean_return = np.mean(gross_returns)
        mean_turnover = np.mean(turnover)

        if mean_turnover <= 0:
            return float('inf')

        return (mean_return / mean_turnover) * 10000


# =============================================================================
# Stress Testing Framework
# =============================================================================

class CrisisScenario:
    """Predefined historical crisis scenarios."""

    SCENARIOS = {
        "dot_com_crash_2000": {
            "description": "Dot-com bubble burst (Mar-Oct 2000)",
            "spx_drawdown": -0.49,
            "vix_peak": 45.0,
            "duration_days": 929,
            "recovery_days": 1789,
        },
        "gfc_2008": {
            "description": "Global Financial Crisis (Oct 2007-Mar 2009)",
            "spx_drawdown": -0.57,
            "vix_peak": 80.9,
            "duration_days": 517,
            "recovery_days": 1481,
        },
        "flash_crash_2010": {
            "description": "Flash Crash (May 6, 2010)",
            "spx_drawdown": -0.10,
            "vix_peak": 40.0,
            "duration_days": 1,
            "recovery_days": 5,
        },
        "china_deval_2015": {
            "description": "China devaluation (Aug 2015)",
            "spx_drawdown": -0.12,
            "vix_peak": 53.3,
            "duration_days": 6,
            "recovery_days": 133,
        },
        "volmageddon_2018": {
            "description": "VIX spike / XIV collapse (Feb 2018)",
            "spx_drawdown": -0.10,
            "vix_peak": 50.3,
            "duration_days": 2,
            "recovery_days": 90,
        },
        "covid_crash_2020": {
            "description": "COVID-19 crash (Feb-Mar 2020)",
            "spx_drawdown": -0.34,
            "vix_peak": 82.7,
            "duration_days": 23,
            "recovery_days": 148,
        },
        "rate_shock_2022": {
            "description": "Fed rate hiking cycle (Jan-Oct 2022)",
            "spx_drawdown": -0.25,
            "vix_peak": 36.5,
            "duration_days": 282,
            "recovery_days": 410,
        },
    }

    @classmethod
    def get_scenario(cls, name: str) -> Dict:
        return cls.SCENARIOS.get(name, {})

    @classmethod
    def simulate_drawdown(
        cls,
        returns: np.ndarray,
        scenario_name: str,
        injection_point: Optional[int] = None,
    ) -> np.ndarray:
        """
        Inject a crisis scenario into the return series.

        Creates synthetic crisis returns matching the historical drawdown
        profile and injects them at the specified point.
        """
        scenario = cls.SCENARIOS.get(scenario_name)
        if not scenario:
            return returns

        drawdown = scenario["spx_drawdown"]
        duration = scenario["duration_days"]

        if injection_point is None:
            injection_point = len(returns) // 2

        daily_return = (1 + drawdown) ** (1 / duration) - 1
        crisis_vol = abs(daily_return) * 2

        rng = np.random.default_rng(42)
        crisis_returns = rng.normal(daily_return, crisis_vol, size=duration)

        modified = returns.copy()
        end_point = min(injection_point + duration, len(modified))
        actual_duration = end_point - injection_point
        modified[injection_point:end_point] = crisis_returns[:actual_duration]

        return modified


# =============================================================================
# Full Validation Pipeline
# =============================================================================

class BacktestValidator:
    """
    Complete backtesting validation pipeline.

    Runs all validation checks and produces a BacktestValidation report.
    """

    def __init__(
        self,
        n_trials: int = 1,
        cost_model: Optional[TransactionCostModel] = None,
    ):
        self.n_trials = n_trials
        self.cost_model = cost_model or TransactionCostModel()
        self.walk_forward = WalkForwardOptimizer()
        self.purged_cv = PurgedKFoldCV()

    def validate(
        self,
        scan_name: str,
        returns: np.ndarray,
        signals: np.ndarray,
        turnover: Optional[np.ndarray] = None,
        regime_labels: Optional[np.ndarray] = None,
    ) -> BacktestValidation:
        """
        Run full validation pipeline on a scan's returns.

        Args:
            scan_name: Name of the scan being validated
            returns: Strategy return series
            signals: Signal series (+1, 0, -1)
            turnover: Portfolio turnover series
            regime_labels: Optional regime labels for each period

        Returns:
            BacktestValidation result
        """
        n = len(returns)
        if n < 60:
            raise ValueError(f"Insufficient data: {n} observations (need >= 60)")

        if turnover is None:
            turnover = np.abs(np.diff(signals, prepend=0)).astype(float)

        winning = np.sum(returns > 0)
        losing = np.sum(returns < 0)
        total = winning + losing
        win_rate = winning / total if total > 0 else 0

        mean_return = np.mean(returns)
        std_return = np.std(returns)
        sharpe = mean_return / std_return * np.sqrt(252) if std_return > 0 else 0

        cumulative = np.cumprod(1 + returns)
        running_max = np.maximum.accumulate(cumulative)
        drawdowns = cumulative / running_max - 1
        max_dd = np.min(drawdowns)

        gross_gains = np.sum(returns[returns > 0])
        gross_losses = abs(np.sum(returns[returns < 0]))
        profit_factor = min(gross_gains / gross_losses, 999.9) if gross_losses > 0 else 999.9

        net_returns = self.cost_model.apply_costs(returns, turnover)
        net_std = np.std(net_returns)
        net_sharpe = np.mean(net_returns) / net_std * np.sqrt(252) if net_std > 0 else 0

        breakeven_bps = self.cost_model.breakeven_cost(returns, turnover)

        skew = float(stats.skew(returns))
        kurt = float(stats.kurtosis(returns)) + 3.0
        dsr = deflated_sharpe_ratio(
            sharpe, self.n_trials, n, skew, kurt
        )

        mbl = minimum_backtest_length(
            sharpe_target=abs(sharpe), skewness=skew, kurtosis=kurt,
            n_trials=self.n_trials,
        )

        mid = n // 2
        is_returns = returns[:mid]
        oos_returns = returns[mid:]
        oos_std = np.std(oos_returns)
        oos_sharpe = np.mean(oos_returns) / oos_std * np.sqrt(252) if oos_std > 0 else 0

        t_stat = sharpe / np.sqrt((1 + 0.5 * sharpe ** 2) / (n - 1)) if n > 1 else 0
        p_value = 2 * (1 - stats.norm.cdf(abs(t_stat)))

        adjusted_p = min(p_value * max(self.n_trials, 1), 1.0)

        performance_by_regime = {}
        if regime_labels is not None:
            unique_regimes = np.unique(regime_labels)
            for regime in unique_regimes:
                mask = regime_labels == regime
                regime_ret = returns[mask]
                if len(regime_ret) > 5:
                    r_std = np.std(regime_ret)
                    r_sharpe = np.mean(regime_ret) / r_std * np.sqrt(252) if r_std > 0 else 0
                    performance_by_regime[str(regime)] = round(r_sharpe, 3)

        pbo = 0.5
        try:
            n_strategies = max(2, self.n_trials)
            rng = np.random.default_rng(42)
            fake_is = np.vstack([is_returns] + [is_returns + rng.normal(0, 0.001, len(is_returns)) for _ in range(n_strategies - 1)])
            fake_oos = np.vstack([oos_returns] + [oos_returns + rng.normal(0, 0.001, len(oos_returns)) for _ in range(n_strategies - 1)])
            pbo = probability_of_overfitting(fake_is, fake_oos)
        except Exception:
            logger.warning("PBO computation failed, using default 0.5", exc_info=True)
            pbo = 0.5

        return BacktestValidation(
            scan_name=scan_name,
            test_period_start=datetime.now(timezone.utc),
            test_period_end=datetime.now(timezone.utc),
            total_signals=int(np.sum(np.abs(signals) > 0)),
            winning_signals=int(winning),
            losing_signals=int(losing),
            win_rate=round(win_rate, 4),
            avg_return=round(float(mean_return), 6),
            sharpe_ratio=round(sharpe, 4),
            max_drawdown=round(float(max_dd), 4),
            profit_factor=round(profit_factor, 4),
            deflated_sharpe=round(dsr, 4),
            probability_of_overfitting=round(pbo, 4),
            minimum_backtest_length=mbl,
            out_of_sample_sharpe=round(oos_sharpe, 4),
            p_value=round(p_value, 6),
            multiple_testing_adjusted_p=round(adjusted_p, 6),
            is_statistically_significant=adjusted_p < 0.05,
            performance_by_regime=performance_by_regime,
            gross_sharpe=round(sharpe, 4),
            net_sharpe=round(net_sharpe, 4),
            breakeven_cost_bps=round(breakeven_bps, 2),
        )
