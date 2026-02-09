"""
Revolution Alpha Engine - Market Breadth & Internals Scanner

Institutional-grade scanner for market-level breadth and internal signals:
- Advance/Decline line and McClellan Oscillator/Summation
- Zweig Breadth Thrust detection
- New Highs/Lows analysis and percent-above-MA breadth
- Volume internals: up/down volume ratio, TRIN (Arms Index)
- Sector rotation via RRG coordinates (Relative Rotation Graphs)
- Credit/yield curve regime signals and recession probability

These are market-wide indicators that provide context for individual
stock signals.  The primary output symbol is "MARKET" or "SPX".
"""

from datetime import datetime
from typing import Optional, Dict, List, Tuple, Any
import logging
import uuid

import numpy as np

from .base import BaseScanner, ScanContext, MarketData, HistoricalData
from .models import (
    ScanResult,
    ScanMode,
    SignalDirection,
    ScannerConfig,
)
from .advanced_models import (
    AdvancedScanResult,
    ScanCategory,
    RegimeContext,
    ExpectedTimeframe,
    BreadthSnapshot,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _ema(series: np.ndarray, span: int) -> np.ndarray:
    """Compute exponential moving average over a 1-D numpy array.

    Uses the standard multiplier  k = 2 / (span + 1)  and initialises
    the EMA with the simple average of the first *span* values.

    Args:
        series: 1-D array of float values.
        span: EMA look-back window (period).

    Returns:
        Array of the same length as *series* with EMA values.
        Elements before the first valid window are filled with NaN.
    """
    if len(series) == 0:
        return np.array([], dtype=np.float64)

    out = np.full_like(series, np.nan, dtype=np.float64)
    k = 2.0 / (span + 1)

    if len(series) < span:
        # Not enough data for a full window -- use available mean as seed
        out[len(series) - 1] = np.nanmean(series)
        for i in range(len(series), len(series)):
            pass  # nothing to iterate
        return out

    # Seed with the SMA of the first *span* values
    out[span - 1] = np.mean(series[:span])
    for i in range(span, len(series)):
        out[i] = series[i] * k + out[i - 1] * (1.0 - k)

    return out


def _safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Return *numerator / denominator*, falling back to *default* on zero."""
    if denominator == 0.0:
        return default
    return numerator / denominator


# ============================================================================
# 1. Advance / Decline Analyzer
# ============================================================================

class AdvanceDeclineAnalyzer:
    """Advance-Decline breadth analysis.

    Provides the cumulative AD line, McClellan Oscillator, McClellan
    Summation Index, Zweig Breadth Thrust indicator, and AD-vs-index
    divergence detection.
    """

    # ------------------------------------------------------------------
    # AD Line
    # ------------------------------------------------------------------
    @staticmethod
    def calculate_ad_line(
        advancers_series: np.ndarray,
        decliners_series: np.ndarray,
    ) -> np.ndarray:
        """Compute the cumulative Advance-Decline line.

        AD_line[t] = cumsum(advancers[t] - decliners[t])

        Args:
            advancers_series: Daily advancing-issue counts.
            decliners_series: Daily declining-issue counts.

        Returns:
            Cumulative AD line (same length as inputs).
        """
        advancers = np.asarray(advancers_series, dtype=np.float64)
        decliners = np.asarray(decliners_series, dtype=np.float64)
        net = advancers - decliners
        return np.cumsum(net)

    # ------------------------------------------------------------------
    # McClellan Oscillator
    # ------------------------------------------------------------------
    @staticmethod
    def mcclellan_oscillator(
        advancers: np.ndarray,
        decliners: np.ndarray,
        fast: int = 19,
        slow: int = 39,
    ) -> np.ndarray:
        """Compute the McClellan Oscillator.

        The ratio-adjusted net-advance is::

            RANA = (A - D) / (A + D) * 1000

        The oscillator is::

            McClellan = EMA(RANA, fast) - EMA(RANA, slow)

        Args:
            advancers: Daily advancing-issue counts.
            decliners: Daily declining-issue counts.
            fast: Fast EMA period (default 19).
            slow: Slow EMA period (default 39).

        Returns:
            McClellan Oscillator array (same length as inputs).
        """
        adv = np.asarray(advancers, dtype=np.float64)
        dec = np.asarray(decliners, dtype=np.float64)

        total = adv + dec
        # Avoid division by zero
        total_safe = np.where(total == 0, 1.0, total)
        rana = (adv - dec) / total_safe * 1000.0

        ema_fast = _ema(rana, fast)
        ema_slow = _ema(rana, slow)

        return ema_fast - ema_slow

    # ------------------------------------------------------------------
    # McClellan Summation Index
    # ------------------------------------------------------------------
    @staticmethod
    def mcclellan_summation(oscillator_series: np.ndarray) -> np.ndarray:
        """Compute the McClellan Summation Index.

        The Summation Index is the running cumulative sum of the McClellan
        Oscillator.  NaN values in the input are treated as zero so the
        cumulative sum is well-defined from the first valid oscillator
        reading onward.

        Args:
            oscillator_series: McClellan Oscillator values.

        Returns:
            Summation Index array (same length as input).
        """
        osc = np.asarray(oscillator_series, dtype=np.float64)
        clean = np.where(np.isnan(osc), 0.0, osc)
        return np.cumsum(clean)

    # ------------------------------------------------------------------
    # Zweig Breadth Thrust
    # ------------------------------------------------------------------
    @staticmethod
    def zweig_breadth_thrust(
        advancers: np.ndarray,
        total: np.ndarray,
        period: int = 10,
    ) -> Dict[str, Any]:
        """Detect a Zweig Breadth Thrust.

        A ZBT fires when the 10-day EMA of the advance ratio
        (A / (A + D)) moves from below 0.40 to above 0.615 within
        *period* trading days.  This is an extremely rare and
        strongly bullish signal.

        Args:
            advancers: Daily advancing-issue counts.
            total: Daily total issues (advancers + decliners + unchanged).
            period: Look-back window for the thrust move (default 10).

        Returns:
            Dictionary with keys:
              - ``thrust_ema``: the 10-day EMA series of the advance ratio
              - ``triggered``: bool, whether the thrust fired on the last bar
              - ``trigger_bar``: index of the trigger bar (or -1)
              - ``from_value``: the low EMA value that started the thrust
              - ``to_value``: the high EMA value that completed the thrust
        """
        adv = np.asarray(advancers, dtype=np.float64)
        tot = np.asarray(total, dtype=np.float64)

        tot_safe = np.where(tot == 0, 1.0, tot)
        ratio = adv / tot_safe

        thrust_ema = _ema(ratio, period)

        triggered = False
        trigger_bar = -1
        from_value = np.nan
        to_value = np.nan

        # Walk the series and look for the transition
        valid_mask = ~np.isnan(thrust_ema)
        valid_indices = np.where(valid_mask)[0]

        if len(valid_indices) >= 2:
            for idx in valid_indices:
                val = thrust_ema[idx]

                # Look back up to *period* bars for a reading below 0.40
                lookback_start = max(valid_indices[0], idx - period)
                window = thrust_ema[lookback_start:idx + 1]
                window_valid = window[~np.isnan(window)]

                if len(window_valid) == 0:
                    continue

                window_min = np.min(window_valid)

                if window_min < 0.40 and val > 0.615:
                    triggered = True
                    trigger_bar = int(idx)
                    from_value = float(window_min)
                    to_value = float(val)
                    # Keep scanning -- we want the most recent trigger

        return {
            "thrust_ema": thrust_ema,
            "triggered": triggered,
            "trigger_bar": trigger_bar,
            "from_value": from_value,
            "to_value": to_value,
        }

    # ------------------------------------------------------------------
    # AD-vs-Index Divergence
    # ------------------------------------------------------------------
    @staticmethod
    def detect_divergence(
        ad_line: np.ndarray,
        price_index: np.ndarray,
        lookback: int = 20,
    ) -> Optional[str]:
        """Detect divergence between the AD line and a price index.

        A **bearish divergence** occurs when the price index makes a new
        high over the look-back window but the AD line does not.

        A **bullish divergence** occurs when the price index makes a new
        low over the look-back window but the AD line does not.

        Args:
            ad_line: Cumulative AD line values.
            price_index: Benchmark index prices (e.g. S&P 500).
            lookback: Number of bars to examine (default 20).

        Returns:
            ``"bullish_divergence"``, ``"bearish_divergence"``, or
            ``None`` if no divergence is detected.
        """
        ad = np.asarray(ad_line, dtype=np.float64)
        price = np.asarray(price_index, dtype=np.float64)

        if len(ad) < lookback + 1 or len(price) < lookback + 1:
            return None

        # Compare the most recent value against the prior window
        price_window = price[-(lookback + 1):-1]
        ad_window = ad[-(lookback + 1):-1]

        price_current = price[-1]
        ad_current = ad[-1]

        # Bearish divergence: price new high, AD line not
        if price_current > np.max(price_window) and ad_current <= np.max(ad_window):
            return "bearish_divergence"

        # Bullish divergence: price new low, AD line not
        if price_current < np.min(price_window) and ad_current >= np.min(ad_window):
            return "bullish_divergence"

        return None


# ============================================================================
# 2. New Highs / Lows Analyzer
# ============================================================================

class NewHighsLowsAnalyzer:
    """Analysis of new-high / new-low data and percent-above-MA breadth."""

    @staticmethod
    def nh_nl_differential(
        new_highs: np.ndarray,
        new_lows: np.ndarray,
    ) -> np.ndarray:
        """Compute the New Highs minus New Lows differential.

        Args:
            new_highs: Daily 52-week new high counts.
            new_lows: Daily 52-week new low counts.

        Returns:
            NH - NL array.
        """
        nh = np.asarray(new_highs, dtype=np.float64)
        nl = np.asarray(new_lows, dtype=np.float64)
        return nh - nl

    @staticmethod
    def nh_nl_ratio(
        new_highs: np.ndarray,
        new_lows: np.ndarray,
    ) -> np.ndarray:
        """Compute the NH / (NH + NL) ratio.

        Values above 0.5 are net-bullish; below 0.5 net-bearish.

        Args:
            new_highs: Daily 52-week new high counts.
            new_lows: Daily 52-week new low counts.

        Returns:
            Ratio array in [0, 1].
        """
        nh = np.asarray(new_highs, dtype=np.float64)
        nl = np.asarray(new_lows, dtype=np.float64)
        total = nh + nl
        total_safe = np.where(total == 0, 1.0, total)
        return nh / total_safe

    @staticmethod
    def percent_above_ma(
        closes_universe: np.ndarray,
        ma_period: int,
    ) -> float:
        """Compute the percentage of stocks trading above their N-day MA.

        Args:
            closes_universe: 2-D array of shape ``(n_stocks, n_bars)``
                where each row is the closing price history for one stock.
            ma_period: Moving-average period (e.g. 20, 50, 100, 200).

        Returns:
            Percentage [0-100] of stocks whose latest close is above their
            own *ma_period*-day simple moving average.  Returns 0.0 when
            input data is insufficient.
        """
        closes = np.asarray(closes_universe, dtype=np.float64)

        if closes.ndim == 1:
            closes = closes.reshape(1, -1)

        n_stocks, n_bars = closes.shape

        if n_bars < ma_period or n_stocks == 0:
            return 0.0

        # SMA of the last *ma_period* bars for each stock
        ma_values = np.mean(closes[:, -ma_period:], axis=1)
        latest_close = closes[:, -1]

        above = np.sum(latest_close > ma_values)
        return float(above / n_stocks * 100.0)

    @staticmethod
    def percent_above_ma_multi(
        closes_universe: np.ndarray,
        periods: List[int] = None,
    ) -> Dict[int, float]:
        """Convenience wrapper: compute ``percent_above_ma`` for several periods.

        Args:
            closes_universe: 2-D array ``(n_stocks, n_bars)``.
            periods: List of MA periods.  Defaults to ``[20, 50, 100, 200]``.

        Returns:
            Dictionary mapping period -> percentage above MA.
        """
        if periods is None:
            periods = [20, 50, 100, 200]
        return {
            p: NewHighsLowsAnalyzer.percent_above_ma(closes_universe, p)
            for p in periods
        }

    @staticmethod
    def bullish_percent_index(
        signals_bullish: int,
        total: int,
    ) -> float:
        """Compute the Bullish Percent Index.

        BPI = (bullish_signals / total) * 100

        Args:
            signals_bullish: Count of stocks on point-and-figure buy signals.
            total: Total stocks in the universe.

        Returns:
            BPI value [0-100].
        """
        if total <= 0:
            return 0.0
        return float(signals_bullish / total * 100.0)


# ============================================================================
# 3. Volume Internals Analyzer
# ============================================================================

class VolumeInternalsAnalyzer:
    """Volume-based market internals: up/down volume, TRIN, concentration."""

    @staticmethod
    def up_down_volume_ratio(
        up_volumes: np.ndarray,
        down_volumes: np.ndarray,
    ) -> np.ndarray:
        """Compute the Up-Volume / Down-Volume ratio.

        Args:
            up_volumes: Aggregate volume of advancing issues.
            down_volumes: Aggregate volume of declining issues.

        Returns:
            Ratio array.  Values > 1 indicate bullish volume breadth.
        """
        up = np.asarray(up_volumes, dtype=np.float64)
        down = np.asarray(down_volumes, dtype=np.float64)
        down_safe = np.where(down == 0, 1.0, down)
        return up / down_safe

    @staticmethod
    def arms_index(
        advancers: float,
        decliners: float,
        up_volume: float,
        down_volume: float,
    ) -> float:
        """Compute the Arms Index (TRIN).

        TRIN = (Advancers / Decliners) / (UpVolume / DownVolume)

        * TRIN < 1  ->  bullish (more volume flowing into advancers)
        * TRIN > 1  ->  bearish (more volume flowing into decliners)
        * TRIN == 1  ->  neutral

        Args:
            advancers: Number of advancing issues.
            decliners: Number of declining issues.
            up_volume: Total volume of advancing issues.
            down_volume: Total volume of declining issues.

        Returns:
            TRIN value (float).
        """
        ad_ratio = _safe_divide(advancers, decliners, default=1.0)
        vol_ratio = _safe_divide(up_volume, down_volume, default=1.0)
        return _safe_divide(ad_ratio, vol_ratio, default=1.0)

    @staticmethod
    def arms_index_series(
        advancers: np.ndarray,
        decliners: np.ndarray,
        up_volumes: np.ndarray,
        down_volumes: np.ndarray,
    ) -> np.ndarray:
        """Vectorised TRIN over a time series.

        Args:
            advancers: Array of daily advancing issue counts.
            decliners: Array of daily declining issue counts.
            up_volumes: Array of daily advancing-issue volume.
            down_volumes: Array of daily declining-issue volume.

        Returns:
            TRIN array (same length as inputs).
        """
        adv = np.asarray(advancers, dtype=np.float64)
        dec = np.asarray(decliners, dtype=np.float64)
        up_v = np.asarray(up_volumes, dtype=np.float64)
        dn_v = np.asarray(down_volumes, dtype=np.float64)

        dec_safe = np.where(dec == 0, 1.0, dec)
        dn_v_safe = np.where(dn_v == 0, 1.0, dn_v)

        ad_ratio = adv / dec_safe
        vol_ratio = up_v / dn_v_safe
        vol_ratio_safe = np.where(vol_ratio == 0, 1.0, vol_ratio)

        return ad_ratio / vol_ratio_safe

    @staticmethod
    def volume_concentration(
        volumes: np.ndarray,
        top_n: int = 10,
    ) -> float:
        """Herfindahl-Hirschman Index of volume concentration.

        Measures how concentrated trading volume is among the top-N
        issues.  A higher value indicates that a handful of stocks are
        dominating volume, which may signal narrow participation.

        Args:
            volumes: 1-D array of per-stock volumes for a single day.
            top_n: Number of top-volume stocks to include (default 10).

        Returns:
            HHI value [0, 1].  Higher = more concentrated.
        """
        vols = np.asarray(volumes, dtype=np.float64)
        total_vol = np.sum(vols)

        if total_vol <= 0 or len(vols) == 0:
            return 0.0

        # Sort descending and take top_n
        sorted_vols = np.sort(vols)[::-1]
        top = sorted_vols[: min(top_n, len(sorted_vols))]
        shares = top / total_vol
        hhi = float(np.sum(shares ** 2))
        return hhi


# ============================================================================
# 4. Sector Rotation Engine
# ============================================================================

class SectorRotationEngine:
    """Relative Rotation Graph (RRG) style sector rotation analysis.

    RRG plots each sector in a coordinate system of:
      * **RS-Ratio** (x-axis) -- relative strength vs benchmark
      * **RS-Momentum** (y-axis) -- rate-of-change of RS-Ratio

    Four quadrants:
      * Leading    (high RS, high mom)
      * Weakening  (high RS, low mom)
      * Lagging    (low RS, low mom)
      * Improving  (low RS, high mom)
    """

    @staticmethod
    def relative_strength(
        sector_returns: np.ndarray,
        benchmark_returns: np.ndarray,
        period: int = 20,
    ) -> np.ndarray:
        """Compute rolling relative-strength ratio.

        RS = cumulative_sector_return / cumulative_benchmark_return
        normalised to 100 at the start of the window.

        Args:
            sector_returns: Daily log or simple returns of the sector.
            benchmark_returns: Daily returns of the benchmark.
            period: Rolling window length.

        Returns:
            RS ratio array (same length as inputs; leading NaNs).
        """
        sec = np.asarray(sector_returns, dtype=np.float64)
        bench = np.asarray(benchmark_returns, dtype=np.float64)
        n = len(sec)

        if n < period:
            return np.full(n, np.nan)

        rs = np.full(n, np.nan)
        for i in range(period - 1, n):
            window_sec = sec[i - period + 1: i + 1]
            window_bench = bench[i - period + 1: i + 1]

            cum_sec = np.prod(1.0 + window_sec)
            cum_bench = np.prod(1.0 + window_bench)

            if cum_bench == 0:
                rs[i] = 100.0
            else:
                rs[i] = (cum_sec / cum_bench) * 100.0

        return rs

    @staticmethod
    def rs_momentum(
        rs_ratio_series: np.ndarray,
        period: int = 10,
    ) -> np.ndarray:
        """Rate of change of the RS-Ratio.

        RS_Mom[t] = RS[t] / RS[t - period] * 100

        Args:
            rs_ratio_series: RS ratio values.
            period: Look-back for rate-of-change (default 10).

        Returns:
            RS-Momentum array (leading NaNs for first *period* values).
        """
        rs = np.asarray(rs_ratio_series, dtype=np.float64)
        n = len(rs)
        mom = np.full(n, np.nan)

        for i in range(period, n):
            prev = rs[i - period]
            if np.isnan(prev) or prev == 0:
                continue
            mom[i] = rs[i] / prev * 100.0

        return mom

    @staticmethod
    def rrg_coordinates(
        sectors_data: Dict[str, np.ndarray],
        benchmark_data: np.ndarray,
        rs_period: int = 20,
        mom_period: int = 10,
    ) -> Dict[str, Tuple[float, float, str]]:
        """Compute RRG coordinates for multiple sectors.

        Args:
            sectors_data: Mapping of sector name -> daily returns array.
            benchmark_data: Daily returns of the benchmark index.
            rs_period: Period for RS-Ratio calculation.
            mom_period: Period for RS-Momentum calculation.

        Returns:
            Dictionary ``{sector: (rs_ratio, rs_momentum, quadrant)}``
            where *quadrant* is one of ``"leading"``, ``"weakening"``,
            ``"lagging"``, or ``"improving"``.
        """
        results: Dict[str, Tuple[float, float, str]] = {}
        bench = np.asarray(benchmark_data, dtype=np.float64)

        for sector, returns in sectors_data.items():
            sec_ret = np.asarray(returns, dtype=np.float64)
            rs = SectorRotationEngine.relative_strength(sec_ret, bench, rs_period)
            mom = SectorRotationEngine.rs_momentum(rs, mom_period)

            # Take the latest valid reading
            rs_val = rs[-1] if len(rs) > 0 and not np.isnan(rs[-1]) else 100.0
            mom_val = mom[-1] if len(mom) > 0 and not np.isnan(mom[-1]) else 100.0

            # Classify quadrant (100 is the neutral pivot)
            if rs_val >= 100.0 and mom_val >= 100.0:
                quadrant = "leading"
            elif rs_val >= 100.0 and mom_val < 100.0:
                quadrant = "weakening"
            elif rs_val < 100.0 and mom_val < 100.0:
                quadrant = "lagging"
            else:
                quadrant = "improving"

            results[sector] = (float(rs_val), float(mom_val), quadrant)

        return results

    @staticmethod
    def detect_rotation(
        rrg_history: List[Dict[str, Tuple[float, float, str]]],
    ) -> Dict[str, str]:
        """Detect sector rotation patterns from a history of RRG snapshots.

        Rotation typically follows the clockwise path:
          Improving -> Leading -> Weakening -> Lagging -> ...

        Args:
            rrg_history: List of RRG coordinate snapshots ordered oldest
                to newest.  Each snapshot is the output of
                ``rrg_coordinates()``.

        Returns:
            Dictionary ``{sector: rotation_description}``.
        """
        if len(rrg_history) < 2:
            return {}

        latest = rrg_history[-1]
        previous = rrg_history[-2]

        rotations: Dict[str, str] = {}
        quadrant_order = ["improving", "leading", "weakening", "lagging"]

        for sector in latest:
            if sector not in previous:
                continue

            _, _, q_now = latest[sector]
            _, _, q_prev = previous[sector]

            if q_now == q_prev:
                rotations[sector] = f"stable_{q_now}"
            else:
                idx_now = quadrant_order.index(q_now) if q_now in quadrant_order else -1
                idx_prev = quadrant_order.index(q_prev) if q_prev in quadrant_order else -1

                if idx_now == (idx_prev + 1) % 4:
                    rotations[sector] = f"clockwise_{q_prev}_to_{q_now}"
                elif idx_prev == (idx_now + 1) % 4:
                    rotations[sector] = f"counter_clockwise_{q_prev}_to_{q_now}"
                else:
                    rotations[sector] = f"jump_{q_prev}_to_{q_now}"

        return rotations


# ============================================================================
# 5. Credit / Yield-Curve Signal Analyzer
# ============================================================================

class CreditSignalAnalyzer:
    """Yield-curve and credit-spread regime analysis.

    Provides slope, regime classification, credit spread signal, and
    a simple probit-based recession probability estimate.
    """

    @staticmethod
    def yield_curve_slope(short_rate: float, long_rate: float) -> float:
        """Simple yield-curve slope (long - short).

        Args:
            short_rate: Short-term rate (e.g. 2-year yield).
            long_rate: Long-term rate (e.g. 10-year yield).

        Returns:
            Slope in percentage points.  Negative = inverted.
        """
        return long_rate - short_rate

    @staticmethod
    def yield_curve_regime(slopes_history: np.ndarray) -> str:
        """Classify the yield-curve regime from recent slope history.

        Regimes:
          * ``"steepening"`` -- slope trending higher
          * ``"flattening"`` -- slope trending lower toward zero
          * ``"inverting"``  -- slope is negative and declining
          * ``"normalizing"`` -- slope is recovering from inversion

        Args:
            slopes_history: Array of recent yield-curve slopes ordered
                oldest to newest (at least 5 observations recommended).

        Returns:
            Regime string.
        """
        slopes = np.asarray(slopes_history, dtype=np.float64)

        if len(slopes) < 2:
            if len(slopes) == 1:
                return "inverting" if slopes[0] < 0 else "steepening"
            return "steepening"

        current = slopes[-1]
        prev = slopes[-2]
        delta = current - prev

        # Use a simple linear regression slope over the window as trend
        n = len(slopes)
        x = np.arange(n, dtype=np.float64)
        mean_x = np.mean(x)
        mean_y = np.mean(slopes)
        cov_xy = np.mean((x - mean_x) * (slopes - mean_y))
        var_x = np.mean((x - mean_x) ** 2)
        trend = cov_xy / var_x if var_x > 0 else 0.0

        if current < 0:
            if trend < 0:
                return "inverting"
            else:
                return "normalizing"
        else:
            if trend > 0:
                return "steepening"
            else:
                return "flattening"

    @staticmethod
    def credit_spread_signal(
        hy_spread: float,
        ig_spread: float,
    ) -> Dict[str, Any]:
        """Analyse high-yield vs investment-grade credit spread.

        A widening HY-IG differential signals increasing credit stress.

        Args:
            hy_spread: High-yield OAS spread (bps).
            ig_spread: Investment-grade OAS spread (bps).

        Returns:
            Dictionary with ``spread_diff``, ``ratio``, and
            ``stress_level`` (``"low"``, ``"moderate"``, ``"elevated"``,
            ``"high"``).
        """
        diff = hy_spread - ig_spread
        ratio = _safe_divide(hy_spread, ig_spread, default=1.0)

        if diff < 200:
            stress = "low"
        elif diff < 400:
            stress = "moderate"
        elif diff < 600:
            stress = "elevated"
        else:
            stress = "high"

        return {
            "spread_diff": diff,
            "ratio": ratio,
            "stress_level": stress,
        }

    @staticmethod
    def recession_probability(
        yield_curve_data: np.ndarray,
    ) -> float:
        """Estimate recession probability using a simple probit-style model.

        Uses the empirical relationship between the 10Y-2Y spread and
        recession onset within 12 months.  The approximation is based on
        the Estrella-Mishkin (1996) model::

            P(recession) = Phi(-0.6 - 1.3 * spread)

        where *spread* is the latest 10Y-2Y slope and Phi is the standard
        normal CDF.

        Args:
            yield_curve_data: Array of recent 10Y-2Y spreads.  Only the
                latest value is used for the point estimate.

        Returns:
            Estimated probability [0, 1].
        """
        data = np.asarray(yield_curve_data, dtype=np.float64)
        if len(data) == 0:
            return 0.0

        spread = data[-1]

        # Probit: P = Phi(alpha + beta * spread)
        alpha = -0.6
        beta = -1.3
        z = alpha + beta * spread

        # Standard normal CDF approximation (good to ~1e-7)
        prob = float(_norm_cdf(z))
        return max(0.0, min(1.0, prob))


def _norm_cdf(x: float) -> float:
    """Standard-normal CDF via an efficient rational approximation.

    Abramowitz & Stegun formula 26.2.17.  Accuracy ~7.5e-8.
    """
    # Constants
    a1 = 0.254829592
    a2 = -0.284496736
    a3 = 1.421413741
    a4 = -1.453152027
    a5 = 1.061405429
    p = 0.3275911

    sign = 1.0
    if x < 0:
        sign = -1.0
    x_abs = abs(x)

    t = 1.0 / (1.0 + p * x_abs)
    y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * np.exp(-x_abs * x_abs / 2.0)

    return 0.5 * (1.0 + sign * y)


# ============================================================================
# 6. Market Breadth Scanner
# ============================================================================

class MarketBreadthScanner(BaseScanner[AdvancedScanResult]):
    """Institutional-grade Market Breadth & Internals scanner.

    Aggregates market-level breadth indicators and emits
    ``AdvancedScanResult`` signals when actionable conditions are met:

    * Zweig Breadth Thrust (strongly bullish)
    * Bearish divergence -- index new high while AD line declines
    * Bullish divergence -- index new low while AD line rises
    * McClellan Oscillator extremes (<-150 oversold, >150 overbought)
    * TRIN extremes (< 0.5 very bullish, > 2.0 very bearish)

    These are market-level signals; the symbol is ``"MARKET"``.
    """

    _CATEGORY = ScanCategory.MARKET_INTERNALS

    def __init__(self, config: Optional[ScannerConfig] = None):
        super().__init__(
            name="market_breadth",
            scan_mode=ScanMode.ALL,
            config=config,
        )
        self._ad_analyzer = AdvanceDeclineAnalyzer()
        self._nhnl_analyzer = NewHighsLowsAnalyzer()
        self._volume_analyzer = VolumeInternalsAnalyzer()

    # ------------------------------------------------------------------
    # Core scan
    # ------------------------------------------------------------------

    async def scan(self, context: ScanContext) -> List[AdvancedScanResult]:
        """Execute breadth scan and return signals.

        The scan inspects the ``context.metadata`` dictionary for
        pre-aggregated market internals data.  Expected keys (all
        arrays ordered oldest -> newest):

        * ``advancers`` -- daily advancing issue counts
        * ``decliners`` -- daily declining issue counts
        * ``unchanged`` -- daily unchanged issue counts (optional)
        * ``up_volume`` -- aggregate advancing-issue volume
        * ``down_volume`` -- aggregate declining-issue volume
        * ``new_highs`` -- daily 52-week new high counts (optional)
        * ``new_lows`` -- daily 52-week new low counts (optional)
        * ``index_prices`` -- benchmark index closing prices (e.g. SPX)
        * ``closes_universe`` -- 2-D array (n_stocks x n_bars) for %MA
        * ``signals_bullish`` / ``signals_total`` -- for BPI (optional)

        Args:
            context: Scan context with populated metadata.

        Returns:
            List of ``AdvancedScanResult`` for any triggered conditions.
        """
        results: List[AdvancedScanResult] = []
        meta = context.metadata

        # ---- Extract required data ----
        advancers = self._to_array(meta.get("advancers"))
        decliners = self._to_array(meta.get("decliners"))
        index_prices = self._to_array(meta.get("index_prices"))

        if advancers is None or decliners is None or len(advancers) < 2:
            self._logger.debug("Insufficient breadth data -- skipping scan")
            return results

        # ---- AD Line & McClellan ----
        ad_line = self._ad_analyzer.calculate_ad_line(advancers, decliners)
        mccl_osc = self._ad_analyzer.mcclellan_oscillator(advancers, decliners)
        mccl_sum = self._ad_analyzer.mcclellan_summation(mccl_osc)

        # Latest valid McClellan Oscillator value
        valid_osc = mccl_osc[~np.isnan(mccl_osc)]
        latest_osc = float(valid_osc[-1]) if len(valid_osc) > 0 else 0.0

        # ---- Zweig Breadth Thrust ----
        unchanged = self._to_array(meta.get("unchanged"))
        if unchanged is not None:
            total = advancers + decliners + unchanged
        else:
            total = advancers + decliners

        zbt = self._ad_analyzer.zweig_breadth_thrust(advancers, total)
        if zbt["triggered"]:
            results.append(self._make_result(
                scan_name="zweig_breadth_thrust",
                direction="BULLISH",
                strength=0.95,
                confidence=0.92,
                expected_move_pct=8.0,
                timeframe=ExpectedTimeframe.POSITION,
                supporting=["Zweig Breadth Thrust triggered",
                             f"EMA rose from {zbt['from_value']:.3f} to {zbt['to_value']:.3f}"],
                math_basis="10-day EMA of A/(A+D) surged from <0.40 to >0.615",
                metadata={"zbt_from": zbt["from_value"], "zbt_to": zbt["to_value"]},
                context=context,
            ))

        # ---- AD Divergence ----
        if index_prices is not None and len(index_prices) >= 21:
            divergence = self._ad_analyzer.detect_divergence(ad_line, index_prices)
            if divergence == "bearish_divergence":
                results.append(self._make_result(
                    scan_name="ad_bearish_divergence",
                    direction="BEARISH",
                    strength=0.75,
                    confidence=0.70,
                    expected_move_pct=-5.0,
                    timeframe=ExpectedTimeframe.SWING,
                    supporting=["Index new high but AD line declining",
                                "Narrow participation warning"],
                    math_basis="Price making higher high while AD line fails to confirm",
                    metadata={"divergence_type": "bearish"},
                    context=context,
                ))
            elif divergence == "bullish_divergence":
                results.append(self._make_result(
                    scan_name="ad_bullish_divergence",
                    direction="BULLISH",
                    strength=0.70,
                    confidence=0.65,
                    expected_move_pct=4.0,
                    timeframe=ExpectedTimeframe.SWING,
                    supporting=["Index new low but AD line rising",
                                "Broadening participation"],
                    math_basis="Price making lower low while AD line holds or rises",
                    metadata={"divergence_type": "bullish"},
                    context=context,
                ))

        # ---- McClellan extremes ----
        if latest_osc > 150:
            results.append(self._make_result(
                scan_name="mcclellan_overbought",
                direction="BEARISH",
                strength=0.60,
                confidence=0.55,
                expected_move_pct=-2.5,
                timeframe=ExpectedTimeframe.SWING,
                supporting=[f"McClellan Oscillator at {latest_osc:.1f} (>150)",
                            "Overbought breadth -- potential pullback"],
                contradicting=["Strong breadth can persist in early-stage rallies"],
                math_basis="McClellan Oscillator = EMA19(RANA) - EMA39(RANA)",
                metadata={"mcclellan_osc": latest_osc},
                context=context,
            ))
        elif latest_osc < -150:
            results.append(self._make_result(
                scan_name="mcclellan_oversold",
                direction="BULLISH",
                strength=0.65,
                confidence=0.60,
                expected_move_pct=3.0,
                timeframe=ExpectedTimeframe.SWING,
                supporting=[f"McClellan Oscillator at {latest_osc:.1f} (<-150)",
                            "Oversold breadth -- potential bounce"],
                contradicting=["Deep oversold can persist in bear markets"],
                math_basis="McClellan Oscillator = EMA19(RANA) - EMA39(RANA)",
                metadata={"mcclellan_osc": latest_osc},
                context=context,
            ))

        # ---- Volume Internals / TRIN ----
        up_vol = self._to_array(meta.get("up_volume"))
        down_vol = self._to_array(meta.get("down_volume"))

        if up_vol is not None and down_vol is not None and len(up_vol) > 0:
            latest_adv = float(advancers[-1])
            latest_dec = float(decliners[-1])
            latest_up_vol = float(up_vol[-1])
            latest_dn_vol = float(down_vol[-1])

            trin = self._volume_analyzer.arms_index(
                latest_adv, latest_dec, latest_up_vol, latest_dn_vol,
            )

            if trin < 0.5:
                results.append(self._make_result(
                    scan_name="trin_extremely_bullish",
                    direction="BULLISH",
                    strength=0.70,
                    confidence=0.65,
                    expected_move_pct=2.0,
                    timeframe=ExpectedTimeframe.INTRADAY,
                    supporting=[f"TRIN at {trin:.2f} -- heavy buying pressure",
                                "Volume strongly concentrated in advancers"],
                    math_basis="TRIN = (A/D) / (UpVol/DownVol); <0.5 extreme bullish",
                    metadata={"trin": trin},
                    context=context,
                ))
            elif trin > 2.0:
                results.append(self._make_result(
                    scan_name="trin_extremely_bearish",
                    direction="BEARISH",
                    strength=0.70,
                    confidence=0.65,
                    expected_move_pct=-2.0,
                    timeframe=ExpectedTimeframe.INTRADAY,
                    supporting=[f"TRIN at {trin:.2f} -- heavy selling pressure",
                                "Volume strongly concentrated in decliners"],
                    contradicting=["Panic selling can mark capitulation lows"],
                    math_basis="TRIN = (A/D) / (UpVol/DownVol); >2.0 extreme bearish",
                    metadata={"trin": trin},
                    context=context,
                ))

        # ---- Percent above MA (informational -- attach to metadata) ----
        closes_universe = meta.get("closes_universe")
        if closes_universe is not None:
            pct_above = self._nhnl_analyzer.percent_above_ma_multi(
                np.asarray(closes_universe, dtype=np.float64),
            )
            # Attach to any result already generated
            for r in results:
                r.metadata["pct_above_ma"] = pct_above

        return results

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_signal(
        self,
        result: AdvancedScanResult,
        context: ScanContext,
    ) -> bool:
        """Validate a breadth signal.

        Market-level signals are always considered valid if they passed
        the confidence threshold in ``post_scan``.
        """
        return result.confidence >= (self.config.min_confidence / 100.0)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_array(data: Any) -> Optional[np.ndarray]:
        """Safely convert metadata value to a numpy float64 array."""
        if data is None:
            return None
        arr = np.asarray(data, dtype=np.float64)
        if arr.ndim == 0:
            return None
        return arr

    def _make_result(
        self,
        scan_name: str,
        direction: str,
        strength: float,
        confidence: float,
        expected_move_pct: float,
        timeframe: ExpectedTimeframe,
        supporting: List[str],
        math_basis: str,
        metadata: Dict[str, Any],
        context: ScanContext,
        contradicting: Optional[List[str]] = None,
    ) -> AdvancedScanResult:
        """Build an ``AdvancedScanResult`` with sensible defaults."""
        # Map market regime from context
        regime_map = {
            "trending_up": RegimeContext.TRENDING_UP,
            "trending_down": RegimeContext.TRENDING_DOWN,
            "ranging": RegimeContext.RANGING,
            "high_volatility": RegimeContext.VOLATILE,
            "low_volatility": RegimeContext.QUIET,
            "breakout": RegimeContext.TRANSITION,
        }
        regime = regime_map.get(context.market_regime.value, RegimeContext.RANGING)

        return AdvancedScanResult(
            scan_id=str(uuid.uuid4()),
            scan_name=scan_name,
            category=self._CATEGORY,
            timestamp=context.timestamp,
            symbol="MARKET",
            signal_direction=direction,
            signal_strength=strength,
            confidence=confidence,
            expected_move_pct=expected_move_pct,
            expected_timeframe=timeframe,
            risk_reward_ratio=0.0,  # market-level, not a direct trade
            supporting_evidence=supporting,
            contradicting_evidence=contradicting or [],
            regime_context=regime,
            mathematical_basis=math_basis,
            historical_accuracy=0.0,
            false_positive_rate=0.0,
            decay_halflife_days=5,
            metadata=metadata,
        )
