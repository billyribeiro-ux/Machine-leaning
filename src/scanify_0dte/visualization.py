"""
SCANIFY SPX 0DTE Options Day Trading Scanner + GEX Scanner -- Visualization Module

Production-grade data preparation and visualization utilities that transform
scanner and GEX engine outputs into chart-ready data structures for frontend
dashboard rendering.  All public methods return plain ``dict`` objects that
are directly JSON-serialisable and compatible with common charting libraries
(Recharts, Chart.js, Highcharts, Plotly, etc.).

No rendering happens here -- this module strictly prepares the data contracts
consumed by the Next.js / Tauri frontend layer.

Colour conventions:
    - Green (#22c55e)  : bullish / positive GEX / gains
    - Red   (#ef4444)  : bearish / negative GEX / losses
    - Amber (#f59e0b)  : neutral / caution / transition zone
    - Blue  (#3b82f6)  : informational / levels / reference
    - Purple(#a855f7)  : gamma flip / key threshold
    - Slate (#64748b)  : inactive / secondary

All monetary values are in USD.  All timestamps are ISO-8601 strings in the
serialised output.
"""

from __future__ import annotations

import logging
import math
import statistics
from datetime import datetime
from typing import Any, Optional

from .models import (
    DirectionScore,
    ExitReason,
    FactorWeights,
    GEXProfile,
    OptionsChain,
    OptionSide,
    ScanSignal,
    ScanType,
    SessionSetup,
    SessionType,
    StrikeGEX,
    StrikeSelection,
    TimeZoneType,
    TradeDirection,
    TradeLog,
)

logger = logging.getLogger(__name__)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def format_currency(value: float) -> str:
    """Format a float as a USD currency string.

    Parameters
    ----------
    value:
        Monetary value in dollars.

    Returns
    -------
    str
        Formatted string, e.g. ``"$1,234.56"`` or ``"-$42.10"``.
    """
    if value < 0:
        return f"-${abs(value):,.2f}"
    return f"${value:,.2f}"


def format_percentage(value: float) -> str:
    """Format a float as a percentage string.

    Parameters
    ----------
    value:
        Value in *percentage points* (e.g. 42.5 means 42.5%).

    Returns
    -------
    str
        Formatted string, e.g. ``"+42.50%"`` or ``"-3.12%"``.
    """
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.2f}%"


def color_for_value(value: float, min_val: float, max_val: float) -> str:
    """Map a numeric value to an RGB hex colour on a red-yellow-green gradient.

    The gradient is:
        ``min_val`` -> red (#ef4444)
        midpoint   -> amber (#f59e0b)
        ``max_val`` -> green (#22c55e)

    Values outside ``[min_val, max_val]`` are clamped.

    Parameters
    ----------
    value:
        The value to map.
    min_val:
        Lower bound of the scale.
    max_val:
        Upper bound of the scale.

    Returns
    -------
    str
        Hex colour string, e.g. ``"#22c55e"``.
    """
    if max_val == min_val:
        return "#f59e0b"

    t = max(0.0, min(1.0, (value - min_val) / (max_val - min_val)))

    # Red   (#ef4444) -> Amber (#f59e0b) -> Green (#22c55e)
    if t <= 0.5:
        ratio = t / 0.5
        r = int(0xEF + (0xF5 - 0xEF) * ratio)
        g = int(0x44 + (0x9E - 0x44) * ratio)
        b = int(0x44 + (0x0B - 0x44) * ratio)
    else:
        ratio = (t - 0.5) / 0.5
        r = int(0xF5 + (0x22 - 0xF5) * ratio)
        g = int(0x9E + (0xC5 - 0x9E) * ratio)
        b = int(0x0B + (0x5E - 0x0B) * ratio)

    r = max(0, min(255, r))
    g = max(0, min(255, g))
    b = max(0, min(255, b))

    return f"#{r:02x}{g:02x}{b:02x}"


def generate_chart_colors(n: int) -> list[str]:
    """Generate *n* visually distinct hex colours for chart series.

    Colours are drawn from a curated palette designed for readability on
    both light and dark backgrounds.  When *n* exceeds the palette size
    the palette wraps cyclically.

    Parameters
    ----------
    n:
        Number of distinct colours required.

    Returns
    -------
    list[str]
        List of hex colour strings.
    """
    palette = [
        "#3b82f6",  # blue
        "#22c55e",  # green
        "#ef4444",  # red
        "#f59e0b",  # amber
        "#a855f7",  # purple
        "#06b6d4",  # cyan
        "#f97316",  # orange
        "#ec4899",  # pink
        "#14b8a6",  # teal
        "#8b5cf6",  # violet
        "#84cc16",  # lime
        "#e11d48",  # rose
        "#0ea5e9",  # sky
        "#d946ef",  # fuchsia
        "#eab308",  # yellow
        "#64748b",  # slate
    ]
    if n <= 0:
        return []
    return [palette[i % len(palette)] for i in range(n)]


def time_axis_labels(timestamps: list[datetime]) -> list[str]:
    """Convert a list of datetime objects to short intraday time labels.

    Produces ``"HH:MM"`` strings suitable for chart X-axis tick labels.

    Parameters
    ----------
    timestamps:
        Datetime objects (timezone-aware or naive).

    Returns
    -------
    list[str]
        Formatted time strings, e.g. ``["09:30", "09:35", ...]``.
    """
    return [ts.strftime("%H:%M") for ts in timestamps]


# ---------------------------------------------------------------------------
# Internal helpers (not part of the public API)
# ---------------------------------------------------------------------------

_SIGNAL_COLORS: dict[str, str] = {
    "BULL": "#22c55e",
    "BEAR": "#ef4444",
    "NEUTRAL": "#f59e0b",
}

_SCAN_TYPE_LABELS: dict[str, str] = {
    "DIRECTIONAL": "Directional",
    "PREMIUM_SELL": "Premium Sell",
    "GAMMA_SCALP": "Gamma Scalp",
}

_SESSION_TYPE_LABELS: dict[str, str] = {
    "TRENDING": "Trending",
    "RANGE": "Range",
    "VOLATILE": "Volatile",
    "SQUEEZE": "Squeeze",
    "EVENT": "Event",
}

_TIME_ZONE_LABELS: dict[str, str] = {
    "PRE_MARKET": "Pre-Market",
    "OPENING_AUCTION": "Open Auction",
    "MORNING_SESSION": "Morning",
    "MIDDAY_LULL": "Midday",
    "AFTERNOON_ACCEL": "Afternoon",
    "POWER_HOUR": "Power Hour",
    "SETTLEMENT_WINDOW": "Settlement",
}


def _iso(ts: datetime) -> str:
    """Render a datetime as ISO-8601 string."""
    return ts.isoformat()


def _safe_div(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Division that returns *default* when denominator is zero."""
    if denominator == 0:
        return default
    return numerator / denominator


def _direction_color(direction: TradeDirection | str) -> str:
    """Resolve a TradeDirection to its display colour."""
    key = direction.value if isinstance(direction, TradeDirection) else str(direction)
    return _SIGNAL_COLORS.get(key, "#64748b")


def _compute_rolling_sharpe(
    returns: list[float],
    window: int = 20,
    risk_free_daily: float = 0.0,
) -> list[Optional[float]]:
    """Compute rolling annualised Sharpe ratio over *window* periods.

    Returns ``None`` for positions where insufficient data exists.
    """
    result: list[Optional[float]] = []
    for i in range(len(returns)):
        if i < window - 1:
            result.append(None)
            continue
        window_returns = returns[i - window + 1: i + 1]
        mean_r = statistics.mean(window_returns) - risk_free_daily
        std_r = statistics.stdev(window_returns) if len(window_returns) > 1 else 0.0
        if std_r == 0:
            result.append(None)
        else:
            result.append(round((mean_r / std_r) * math.sqrt(252), 4))
    return result


# =============================================================================
# 1. GEX VISUALIZATION
# =============================================================================


class GEXVisualization:
    """Prepares GEX data for frontend chart rendering.

    All methods are stateless class methods that accept model instances and
    return plain dictionaries ready for JSON serialisation.
    """

    # -----------------------------------------------------------------
    # 1a) GEX Bar Chart
    # -----------------------------------------------------------------

    @staticmethod
    def gex_bar_chart(profile: GEXProfile, spot: float) -> dict[str, Any]:
        """Generate GEX bar chart data.

        Produces per-strike call/put/net GEX values for a grouped or
        stacked bar chart, annotated with the key structural levels.

        Parameters
        ----------
        profile:
            Current GEX profile snapshot.
        spot:
            Current SPX spot price.

        Returns
        -------
        dict
            Chart-ready dictionary with strikes on the X-axis and
            call_gex (green), put_gex (red), and net_gex series.
        """
        sorted_strikes = sorted(profile.strikes, key=lambda s: s.strike)

        strikes: list[float] = []
        call_gex: list[float] = []
        put_gex: list[float] = []
        net_gex: list[float] = []

        for sg in sorted_strikes:
            strikes.append(sg.strike)
            call_gex.append(round(sg.dealer_gamma_call, 4))
            put_gex.append(round(sg.dealer_gamma_put, 4))
            net_gex.append(round(sg.net_gex, 4))

        # Build annotations for key levels
        annotations: list[dict[str, Any]] = [
            {
                "strike": profile.gamma_flip_level,
                "label": "Gamma Flip",
                "color": "#a855f7",
            },
            {
                "strike": profile.call_wall,
                "label": "Call Wall",
                "color": "#22c55e",
            },
            {
                "strike": profile.put_wall,
                "label": "Put Wall",
                "color": "#ef4444",
            },
            {
                "strike": profile.max_pain,
                "label": "Max Pain",
                "color": "#3b82f6",
            },
            {
                "strike": profile.vol_trigger,
                "label": "Vol Trigger",
                "color": "#06b6d4",
            },
        ]

        return {
            "chart_type": "gex_bar",
            "strikes": strikes,
            "call_gex": call_gex,
            "put_gex": put_gex,
            "net_gex": net_gex,
            "spot": round(spot, 2),
            "gamma_flip": round(profile.gamma_flip_level, 2),
            "call_wall": round(profile.call_wall, 2),
            "put_wall": round(profile.put_wall, 2),
            "transition_zone": [
                round(profile.transition_zone_lower, 2),
                round(profile.transition_zone_upper, 2),
            ],
            "total_net_gex": round(profile.total_net_gex, 4),
            "regime": "positive" if profile.is_positive_gamma_regime else "negative",
            "annotations": annotations,
            "colors": {
                "call_gex": "#22c55e",
                "put_gex": "#ef4444",
                "net_gex": "#3b82f6",
            },
            "timestamp": _iso(profile.timestamp),
        }

    # -----------------------------------------------------------------
    # 1b) GEX Heatmap
    # -----------------------------------------------------------------

    @staticmethod
    def gex_heatmap(profiles_history: list[GEXProfile]) -> dict[str, Any]:
        """Generate GEX heatmap data over time.

        X-axis is time, Y-axis is strike, colour intensity encodes net GEX.
        Suitable for a 2-D heatmap / contour chart.

        Parameters
        ----------
        profiles_history:
            Time-ordered list of GEX profile snapshots (oldest first).

        Returns
        -------
        dict
            ``timestamps`` (list[str]), ``strikes`` (sorted unique),
            ``values`` (2-D nested list, rows=strikes, cols=timestamps),
            and ``color_scale``.
        """
        if not profiles_history:
            return {
                "chart_type": "gex_heatmap",
                "timestamps": [],
                "strikes": [],
                "values": [],
                "color_scale": "RdYlGn",
            }

        timestamps: list[str] = [_iso(p.timestamp) for p in profiles_history]
        time_labels: list[str] = time_axis_labels(
            [p.timestamp for p in profiles_history]
        )

        # Collect the union of all strikes across snapshots
        all_strikes: set[float] = set()
        for profile in profiles_history:
            for sg in profile.strikes:
                all_strikes.add(sg.strike)
        sorted_all_strikes = sorted(all_strikes)

        # Build the 2-D values matrix (rows=strikes, cols=time)
        values: list[list[float]] = []
        for strike in sorted_all_strikes:
            row: list[float] = []
            for profile in profiles_history:
                gex_at_strike = 0.0
                for sg in profile.strikes:
                    if sg.strike == strike:
                        gex_at_strike = sg.net_gex
                        break
                row.append(round(gex_at_strike, 4))
            values.append(row)

        # Compute min/max for colour scale normalisation
        flat = [v for row in values for v in row]
        min_val = min(flat) if flat else 0.0
        max_val = max(flat) if flat else 0.0

        return {
            "chart_type": "gex_heatmap",
            "timestamps": timestamps,
            "time_labels": time_labels,
            "strikes": sorted_all_strikes,
            "values": values,
            "color_scale": "RdYlGn",
            "value_range": {
                "min": round(min_val, 4),
                "max": round(max_val, 4),
            },
        }

    # -----------------------------------------------------------------
    # 1c) Gamma Flip Timeline
    # -----------------------------------------------------------------

    @staticmethod
    def gamma_flip_timeline(
        profiles_history: list[GEXProfile],
        spot_prices: Optional[list[float]] = None,
    ) -> dict[str, Any]:
        """Track the gamma flip level over the trading day.

        Overlays the gamma flip level with spot price so the user can
        see when spot crosses the flip and the regime changes.

        Parameters
        ----------
        profiles_history:
            Time-ordered GEX profile snapshots.
        spot_prices:
            Corresponding spot prices aligned to each profile timestamp.
            If ``None``, spot prices are omitted from the output.

        Returns
        -------
        dict
            ``timestamps``, ``gamma_flip``, ``spot_price``, ``regime``.
        """
        timestamps: list[str] = []
        gamma_flip: list[float] = []
        regime: list[str] = []
        spot_series: list[Optional[float]] = []

        for idx, profile in enumerate(profiles_history):
            timestamps.append(_iso(profile.timestamp))
            gamma_flip.append(round(profile.gamma_flip_level, 2))
            regime.append(
                "positive" if profile.is_positive_gamma_regime else "negative"
            )
            if spot_prices and idx < len(spot_prices):
                spot_series.append(round(spot_prices[idx], 2))
            else:
                spot_series.append(None)

        return {
            "chart_type": "gamma_flip_timeline",
            "timestamps": timestamps,
            "time_labels": time_axis_labels(
                [p.timestamp for p in profiles_history]
            ),
            "gamma_flip": gamma_flip,
            "spot_price": spot_series,
            "regime": regime,
            "colors": {
                "gamma_flip": "#a855f7",
                "spot_price": "#3b82f6",
                "positive_regime": "#22c55e",
                "negative_regime": "#ef4444",
            },
        }

    # -----------------------------------------------------------------
    # 1d) Key Levels Diagram
    # -----------------------------------------------------------------

    @staticmethod
    def key_levels_diagram(
        profile: GEXProfile,
        session_setup: SessionSetup,
        spot: float,
    ) -> dict[str, Any]:
        """Generate key levels diagram data.

        Renders a horizontal-level diagram showing GEX structural levels,
        expected move boundaries, prior-day references, and the current
        spot price in a single unified view.

        Parameters
        ----------
        profile:
            Current GEX profile.
        session_setup:
            Today's pre-market session setup.
        spot:
            Current SPX spot price.

        Returns
        -------
        dict
            All levels with type classifications, colours, and metadata.
        """
        kl = session_setup.key_levels
        em = session_setup.expected_move

        em_upper = round(spot + em.final_1sigma, 2)
        em_lower = round(spot - em.final_1sigma, 2)
        em_upper_2s = round(spot + em.final_2sigma, 2)
        em_lower_2s = round(spot - em.final_2sigma, 2)

        levels: list[dict[str, Any]] = [
            # GEX-derived levels
            {
                "price": round(profile.gamma_flip_level, 2),
                "label": "Gamma Flip",
                "type": "gex",
                "color": "#a855f7",
                "style": "solid",
                "importance": "primary",
            },
            {
                "price": round(profile.call_wall, 2),
                "label": "Call Wall",
                "type": "gex",
                "color": "#22c55e",
                "style": "solid",
                "importance": "primary",
            },
            {
                "price": round(profile.put_wall, 2),
                "label": "Put Wall",
                "type": "gex",
                "color": "#ef4444",
                "style": "solid",
                "importance": "primary",
            },
            {
                "price": round(profile.max_pain, 2),
                "label": "Max Pain",
                "type": "gex",
                "color": "#3b82f6",
                "style": "dashed",
                "importance": "secondary",
            },
            {
                "price": round(profile.vol_trigger, 2),
                "label": "Vol Trigger",
                "type": "gex",
                "color": "#06b6d4",
                "style": "dashed",
                "importance": "secondary",
            },
            {
                "price": round(profile.plus_gex, 2),
                "label": "+GEX",
                "type": "gex",
                "color": "#22c55e",
                "style": "dotted",
                "importance": "tertiary",
            },
            {
                "price": round(profile.minus_gex, 2),
                "label": "-GEX",
                "type": "gex",
                "color": "#ef4444",
                "style": "dotted",
                "importance": "tertiary",
            },
            # Expected move boundaries
            {
                "price": em_upper,
                "label": "EM +1\u03c3",
                "type": "expected_move",
                "color": "#f59e0b",
                "style": "dashed",
                "importance": "primary",
            },
            {
                "price": em_lower,
                "label": "EM -1\u03c3",
                "type": "expected_move",
                "color": "#f59e0b",
                "style": "dashed",
                "importance": "primary",
            },
            {
                "price": em_upper_2s,
                "label": "EM +2\u03c3",
                "type": "expected_move",
                "color": "#f59e0b",
                "style": "dotted",
                "importance": "tertiary",
            },
            {
                "price": em_lower_2s,
                "label": "EM -2\u03c3",
                "type": "expected_move",
                "color": "#f59e0b",
                "style": "dotted",
                "importance": "tertiary",
            },
            # Prior day levels
            {
                "price": round(kl.prior_high, 2),
                "label": "Prior High",
                "type": "prior_day",
                "color": "#64748b",
                "style": "dashed",
                "importance": "secondary",
            },
            {
                "price": round(kl.prior_low, 2),
                "label": "Prior Low",
                "type": "prior_day",
                "color": "#64748b",
                "style": "dashed",
                "importance": "secondary",
            },
            {
                "price": round(kl.prior_close, 2),
                "label": "Prior Close",
                "type": "prior_day",
                "color": "#64748b",
                "style": "solid",
                "importance": "secondary",
            },
            {
                "price": round(kl.prior_vwap, 2),
                "label": "Prior VWAP",
                "type": "prior_day",
                "color": "#8b5cf6",
                "style": "dashed",
                "importance": "secondary",
            },
            # Overnight levels
            {
                "price": round(kl.overnight_high, 2),
                "label": "Overnight High",
                "type": "overnight",
                "color": "#06b6d4",
                "style": "dotted",
                "importance": "tertiary",
            },
            {
                "price": round(kl.overnight_low, 2),
                "label": "Overnight Low",
                "type": "overnight",
                "color": "#06b6d4",
                "style": "dotted",
                "importance": "tertiary",
            },
        ]

        # Add moving averages
        for ma_label, ma_price in kl.moving_averages.items():
            levels.append(
                {
                    "price": round(ma_price, 2),
                    "label": ma_label,
                    "type": "technical",
                    "color": "#8b5cf6",
                    "style": "dotted",
                    "importance": "tertiary",
                }
            )

        # Add round-number levels
        for rl in kl.round_levels:
            levels.append(
                {
                    "price": round(rl, 2),
                    "label": f"{int(rl)}",
                    "type": "round_number",
                    "color": "#94a3b8",
                    "style": "dotted",
                    "importance": "tertiary",
                }
            )

        # Sort all levels by price for orderly rendering
        levels.sort(key=lambda lv: lv["price"])

        return {
            "chart_type": "key_levels",
            "spot": round(spot, 2),
            "levels": levels,
            "transition_zone": {
                "upper": round(profile.transition_zone_upper, 2),
                "lower": round(profile.transition_zone_lower, 2),
                "color": "#f59e0b",
                "opacity": 0.15,
            },
            "expected_move": {
                "upper_1s": em_upper,
                "lower_1s": em_lower,
                "upper_2s": em_upper_2s,
                "lower_2s": em_lower_2s,
            },
            "regime": "positive" if profile.is_positive_gamma_regime else "negative",
            "session_type": session_setup.session_type.value,
            "gap_analysis": {
                "gap_pct": round(session_setup.gap_analysis.gap_pct, 4),
                "classification": session_setup.gap_analysis.classification.value,
            },
            "timestamp": _iso(profile.timestamp),
        }


# =============================================================================
# 2. SCANNER VISUALIZATION
# =============================================================================


class ScannerVisualization:
    """Prepares scanner signal data for frontend rendering.

    Transforms directional scores, scan signals, and strike selections
    into chart-ready payloads for the scanner dashboard.
    """

    # -----------------------------------------------------------------
    # 2a) Direction Score Gauge
    # -----------------------------------------------------------------

    @staticmethod
    def direction_score_gauge(score: DirectionScore) -> dict[str, Any]:
        """Generate direction score gauge data (-100 to +100).

        Suitable for a semicircular gauge, speedometer, or horizontal
        bar gauge with factor breakdown.

        Parameters
        ----------
        score:
            The composite directional score output.

        Returns
        -------
        dict
            Gauge value, factors breakdown, colour, and threshold lines.
        """
        factors = [
            {
                "name": "Market Internals",
                "score": round(score.market_internals_score, 2),
                "weight": 0.30,
                "color": color_for_value(
                    score.market_internals_score, -100, 100
                ),
            },
            {
                "name": "Options Flow",
                "score": round(score.options_flow_score, 2),
                "weight": 0.25,
                "color": color_for_value(
                    score.options_flow_score, -100, 100
                ),
            },
            {
                "name": "Price Action",
                "score": round(score.price_action_score, 2),
                "weight": 0.20,
                "color": color_for_value(
                    score.price_action_score, -100, 100
                ),
            },
            {
                "name": "GEX Structure",
                "score": round(score.gex_structure_score, 2),
                "weight": 0.15,
                "color": color_for_value(
                    score.gex_structure_score, -100, 100
                ),
            },
            {
                "name": "Cross-Asset",
                "score": round(score.cross_asset_score, 2),
                "weight": 0.10,
                "color": color_for_value(
                    score.cross_asset_score, -100, 100
                ),
            },
        ]

        total = round(score.total_score, 2)

        return {
            "chart_type": "direction_gauge",
            "total_score": total,
            "signal": score.signal.value,
            "confidence": round(score.confidence, 2),
            "factors_agreeing": score.factors_agreeing,
            "has_opposing_factor": score.has_opposing_factor,
            "is_high_conviction": score.is_high_conviction,
            "is_conflicted": score.is_conflicted,
            "factors": factors,
            "threshold_lines": [-65, -40, 0, 40, 65],
            "color": _direction_color(score.signal),
            "range": {"min": -100, "max": 100},
            "zones": [
                {"min": -100, "max": -65, "label": "Strong Bear", "color": "#dc2626"},
                {"min": -65, "max": -40, "label": "Bearish", "color": "#ef4444"},
                {"min": -40, "max": 0, "label": "Lean Bear", "color": "#f87171"},
                {"min": 0, "max": 40, "label": "Lean Bull", "color": "#86efac"},
                {"min": 40, "max": 65, "label": "Bullish", "color": "#22c55e"},
                {"min": 65, "max": 100, "label": "Strong Bull", "color": "#16a34a"},
            ],
            "timestamp": _iso(score.timestamp),
        }

    # -----------------------------------------------------------------
    # 2b) Signal Timeline
    # -----------------------------------------------------------------

    @staticmethod
    def signal_timeline(signals_history: list[ScanSignal]) -> dict[str, Any]:
        """Generate signal timeline for the trading day.

        Renders a timeline with each scan signal as a marker, showing
        entry points, scan types, direction, and risk/reward at each
        signal.

        Parameters
        ----------
        signals_history:
            Time-ordered list of scan signals.

        Returns
        -------
        dict
            Timeline events with associated metadata.
        """
        events: list[dict[str, Any]] = []

        for sig in signals_history:
            event: dict[str, Any] = {
                "timestamp": _iso(sig.timestamp),
                "scan_type": sig.scan_type.value,
                "scan_type_label": _SCAN_TYPE_LABELS.get(
                    sig.scan_type.value, sig.scan_type.value
                ),
                "direction": sig.direction.value,
                "direction_color": _direction_color(sig.direction),
                "entry_price": round(sig.entry_price, 2),
                "stop_loss": round(sig.stop_loss, 2),
                "profit_target": round(sig.profit_target, 2),
                "risk_reward_ratio": round(sig.risk_reward_ratio, 2),
                "max_risk": format_currency(sig.max_risk),
                "expected_reward": format_currency(sig.expected_reward),
                "contracts": sig.contracts,
                "position_type": sig.position_type.value,
                "time_zone": sig.time_zone.value,
                "time_zone_label": _TIME_ZONE_LABELS.get(
                    sig.time_zone.value, sig.time_zone.value
                ),
                "session_type": sig.session_type.value,
                "composite_score": round(sig.direction_score.total_score, 2),
                "confidence": round(sig.direction_score.confidence, 2),
                "is_favorable_rr": sig.is_favorable_rr,
            }

            if sig.strike_selection:
                event["strike"] = sig.strike_selection.strike
                event["option_type"] = sig.strike_selection.option_type.value
                event["delta"] = round(sig.strike_selection.delta, 4)
                event["iv"] = round(sig.strike_selection.iv, 4)

            events.append(event)

        return {
            "chart_type": "signal_timeline",
            "events": events,
            "total_signals": len(events),
            "scan_type_counts": _count_by_key(events, "scan_type"),
            "direction_counts": _count_by_key(events, "direction"),
            "colors": {
                "DIRECTIONAL": "#3b82f6",
                "PREMIUM_SELL": "#f59e0b",
                "GAMMA_SCALP": "#a855f7",
            },
        }

    # -----------------------------------------------------------------
    # 2c) Factor Contribution Chart
    # -----------------------------------------------------------------

    @staticmethod
    def factor_contribution_chart(
        scores_history: list[DirectionScore],
    ) -> dict[str, Any]:
        """Stacked area chart of factor contributions over time.

        Each factor's weighted contribution is displayed as a stacked
        area so the user can see which factors are driving the score.

        Parameters
        ----------
        scores_history:
            Time-ordered list of composite direction scores.

        Returns
        -------
        dict
            Time series for each factor and the composite total.
        """
        timestamps: list[str] = []
        time_labels: list[str] = []
        market_internals: list[float] = []
        options_flow: list[float] = []
        price_action: list[float] = []
        gex_structure: list[float] = []
        cross_asset: list[float] = []
        total: list[float] = []

        for ds in scores_history:
            timestamps.append(_iso(ds.timestamp))
            time_labels.append(ds.timestamp.strftime("%H:%M"))
            market_internals.append(round(ds.market_internals_score, 2))
            options_flow.append(round(ds.options_flow_score, 2))
            price_action.append(round(ds.price_action_score, 2))
            gex_structure.append(round(ds.gex_structure_score, 2))
            cross_asset.append(round(ds.cross_asset_score, 2))
            total.append(round(ds.total_score, 2))

        return {
            "chart_type": "factor_contribution",
            "timestamps": timestamps,
            "time_labels": time_labels,
            "series": [
                {
                    "name": "Market Internals",
                    "key": "market_internals",
                    "data": market_internals,
                    "color": "#3b82f6",
                },
                {
                    "name": "Options Flow",
                    "key": "options_flow",
                    "data": options_flow,
                    "color": "#22c55e",
                },
                {
                    "name": "Price Action",
                    "key": "price_action",
                    "data": price_action,
                    "color": "#f59e0b",
                },
                {
                    "name": "GEX Structure",
                    "key": "gex_structure",
                    "data": gex_structure,
                    "color": "#a855f7",
                },
                {
                    "name": "Cross-Asset",
                    "key": "cross_asset",
                    "data": cross_asset,
                    "color": "#06b6d4",
                },
            ],
            "total": total,
            "total_color": "#64748b",
            "data_points": len(timestamps),
        }

    # -----------------------------------------------------------------
    # 2d) Strike Selection Overlay
    # -----------------------------------------------------------------

    @staticmethod
    def strike_selection_overlay(
        chain: OptionsChain,
        selected_strike: StrikeSelection,
        spot: float,
        em_upper: float,
        em_lower: float,
        key_levels: Optional[dict[str, float]] = None,
    ) -> dict[str, Any]:
        """Show the selected strike in context of the chain and key levels.

        Produces a scatter / strip plot showing all liquid strikes, the
        selected strike highlighted, and overlay lines for expected move
        boundaries and key levels.

        Parameters
        ----------
        chain:
            The current options chain.
        selected_strike:
            The strike the scanner selected for entry.
        spot:
            Current SPX spot price.
        em_upper:
            Upper expected move boundary.
        em_lower:
            Lower expected move boundary.
        key_levels:
            Optional dict of additional key levels (label -> price).

        Returns
        -------
        dict
            Strike map with selection, boundaries, and annotations.
        """
        # Build per-strike data for the chain
        chain_data: list[dict[str, Any]] = []
        for quote in chain.quotes:
            chain_data.append(
                {
                    "strike": quote.strike,
                    "option_type": quote.option_type.value,
                    "bid": round(quote.bid, 2),
                    "ask": round(quote.ask, 2),
                    "mid": round(quote.mid, 2),
                    "volume": quote.volume,
                    "oi": quote.open_interest,
                    "iv": round(quote.implied_vol, 4),
                    "delta": round(quote.delta, 4),
                    "gamma": round(quote.gamma, 6),
                    "is_liquid": quote.is_liquid,
                }
            )

        # Selected strike highlight
        selection: dict[str, Any] = {
            "strike": selected_strike.strike,
            "option_type": selected_strike.option_type.value,
            "delta": round(selected_strike.delta, 4),
            "iv": round(selected_strike.iv, 4),
            "bid": round(selected_strike.bid, 2),
            "ask": round(selected_strike.ask, 2),
            "mid": round(selected_strike.mid, 2),
            "spread_width": round(selected_strike.spread_width, 2),
            "oi": selected_strike.oi,
            "volume": selected_strike.volume,
            "is_liquid": selected_strike.is_liquid,
            "distance_from_spot": round(selected_strike.distance_from_spot, 2),
            "moneyness": round(selected_strike.moneyness, 6),
            "cost_per_point": (
                round(selected_strike.cost_per_point, 2)
                if selected_strike.cost_per_point != float("inf")
                else None
            ),
            "color": "#f59e0b",
        }

        # Overlay lines
        overlays: list[dict[str, Any]] = [
            {
                "price": round(spot, 2),
                "label": "Spot",
                "color": "#3b82f6",
                "style": "solid",
            },
            {
                "price": round(em_upper, 2),
                "label": "EM Upper",
                "color": "#f59e0b",
                "style": "dashed",
            },
            {
                "price": round(em_lower, 2),
                "label": "EM Lower",
                "color": "#f59e0b",
                "style": "dashed",
            },
        ]

        if key_levels:
            for label, price in key_levels.items():
                overlays.append(
                    {
                        "price": round(price, 2),
                        "label": label,
                        "color": "#a855f7",
                        "style": "dotted",
                    }
                )

        return {
            "chart_type": "strike_selection",
            "chain": chain_data,
            "selected": selection,
            "spot": round(spot, 2),
            "em_upper": round(em_upper, 2),
            "em_lower": round(em_lower, 2),
            "atm_strike": chain.atm_strike(),
            "overlays": overlays,
            "total_strikes": len(chain.strikes),
            "timestamp": _iso(chain.timestamp),
        }


# =============================================================================
# 3. PERFORMANCE VISUALIZATION
# =============================================================================


class PerformanceVisualization:
    """Prepares performance and P&L data for frontend rendering.

    Transforms trade logs and position data into equity curves, P&L
    distributions, win-rate breakdowns, and risk metric cards.
    """

    # -----------------------------------------------------------------
    # 3a) Intraday P&L Curve
    # -----------------------------------------------------------------

    @staticmethod
    def intraday_pnl_curve(
        trades: list[TradeLog],
        positions: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        """Intraday P&L curve with drawdown shading.

        Builds a cumulative P&L line from closed trades, with a shaded
        drawdown area underneath.  Open positions contribute unrealised
        P&L when ``positions`` is provided.

        Parameters
        ----------
        trades:
            Closed trades with ``pnl_dollars`` populated.
        positions:
            Optional list of open position dicts with keys
            ``timestamp`` (datetime) and ``unrealised_pnl`` (float).

        Returns
        -------
        dict
            Time-indexed cumulative P&L and drawdown series.
        """
        # Sort trades by exit time
        closed = [t for t in trades if t.timestamp_exit and t.pnl_dollars is not None]
        closed.sort(key=lambda t: t.timestamp_exit)  # type: ignore[arg-type]

        timestamps: list[str] = []
        time_labels: list[str] = []
        cumulative_pnl: list[float] = []
        trade_pnl: list[float] = []
        running = 0.0

        for t in closed:
            ts = t.timestamp_exit
            assert ts is not None
            timestamps.append(_iso(ts))
            time_labels.append(ts.strftime("%H:%M"))
            running += t.pnl_dollars  # type: ignore[operator]
            cumulative_pnl.append(round(running, 2))
            trade_pnl.append(round(t.pnl_dollars, 2))  # type: ignore[arg-type]

        # Inject open-position unrealised P&L points
        if positions:
            for pos in positions:
                ts = pos.get("timestamp")
                upnl = pos.get("unrealised_pnl", 0.0)
                if ts and isinstance(ts, datetime):
                    timestamps.append(_iso(ts))
                    time_labels.append(ts.strftime("%H:%M"))
                    cumulative_pnl.append(round(running + upnl, 2))
                    trade_pnl.append(round(upnl, 2))

        # Compute drawdown series
        peak = 0.0
        drawdown: list[float] = []
        for pnl_val in cumulative_pnl:
            peak = max(peak, pnl_val)
            dd = pnl_val - peak
            drawdown.append(round(dd, 2))

        max_dd = min(drawdown) if drawdown else 0.0

        return {
            "chart_type": "intraday_pnl",
            "timestamps": timestamps,
            "time_labels": time_labels,
            "cumulative_pnl": cumulative_pnl,
            "trade_pnl": trade_pnl,
            "drawdown": drawdown,
            "max_drawdown": round(max_dd, 2),
            "final_pnl": cumulative_pnl[-1] if cumulative_pnl else 0.0,
            "final_pnl_formatted": format_currency(
                cumulative_pnl[-1] if cumulative_pnl else 0.0
            ),
            "total_trades": len(closed),
            "colors": {
                "pnl_line": "#3b82f6",
                "drawdown_fill": "#ef4444",
                "zero_line": "#64748b",
                "positive_fill": "#22c55e",
            },
        }

    # -----------------------------------------------------------------
    # 3b) P&L Distribution
    # -----------------------------------------------------------------

    @staticmethod
    def pnl_distribution(trades: list[TradeLog]) -> dict[str, Any]:
        """P&L distribution histogram with statistical markers.

        Parameters
        ----------
        trades:
            Closed trades with ``pnl_dollars`` populated.

        Returns
        -------
        dict
            Histogram bins with mean, median, std, and percentile markers.
        """
        pnl_values = [
            t.pnl_dollars for t in trades
            if t.pnl_dollars is not None
        ]

        if not pnl_values:
            return {
                "chart_type": "pnl_distribution",
                "bins": [],
                "statistics": {},
                "markers": [],
            }

        mean_pnl = statistics.mean(pnl_values)
        median_pnl = statistics.median(pnl_values)
        stdev_pnl = statistics.stdev(pnl_values) if len(pnl_values) > 1 else 0.0
        min_pnl = min(pnl_values)
        max_pnl = max(pnl_values)

        # Compute histogram bins
        num_bins = min(max(10, len(pnl_values) // 5), 50)
        if max_pnl == min_pnl:
            bins = [{"x_start": min_pnl - 1, "x_end": max_pnl + 1, "count": len(pnl_values)}]
        else:
            bin_width = (max_pnl - min_pnl) / num_bins
            bins: list[dict[str, Any]] = []
            for i in range(num_bins):
                x_start = min_pnl + i * bin_width
                x_end = min_pnl + (i + 1) * bin_width
                count = sum(
                    1 for v in pnl_values
                    if (x_start <= v < x_end) or (i == num_bins - 1 and v == x_end)
                )
                bins.append(
                    {
                        "x_start": round(x_start, 2),
                        "x_end": round(x_end, 2),
                        "x_mid": round((x_start + x_end) / 2, 2),
                        "count": count,
                        "color": "#22c55e" if (x_start + x_end) / 2 >= 0 else "#ef4444",
                    }
                )

        # Percentiles
        sorted_pnl = sorted(pnl_values)
        p5 = _percentile(sorted_pnl, 5)
        p25 = _percentile(sorted_pnl, 25)
        p75 = _percentile(sorted_pnl, 75)
        p95 = _percentile(sorted_pnl, 95)

        markers = [
            {"value": round(mean_pnl, 2), "label": "Mean", "color": "#3b82f6", "style": "solid"},
            {"value": round(median_pnl, 2), "label": "Median", "color": "#a855f7", "style": "solid"},
            {"value": round(mean_pnl - stdev_pnl, 2), "label": "-1\u03c3", "color": "#ef4444", "style": "dashed"},
            {"value": round(mean_pnl + stdev_pnl, 2), "label": "+1\u03c3", "color": "#22c55e", "style": "dashed"},
        ]

        return {
            "chart_type": "pnl_distribution",
            "bins": bins,
            "statistics": {
                "mean": round(mean_pnl, 2),
                "mean_formatted": format_currency(mean_pnl),
                "median": round(median_pnl, 2),
                "median_formatted": format_currency(median_pnl),
                "stdev": round(stdev_pnl, 2),
                "min": round(min_pnl, 2),
                "max": round(max_pnl, 2),
                "count": len(pnl_values),
                "skew": round(_compute_skewness(pnl_values), 4),
                "percentiles": {
                    "p5": round(p5, 2),
                    "p25": round(p25, 2),
                    "p75": round(p75, 2),
                    "p95": round(p95, 2),
                },
            },
            "markers": markers,
        }

    # -----------------------------------------------------------------
    # 3c) Win Rate by Category
    # -----------------------------------------------------------------

    @staticmethod
    def win_rate_by_category(trades: list[TradeLog]) -> dict[str, Any]:
        """Win rates broken down by scan type, time zone, and session type.

        Parameters
        ----------
        trades:
            Closed trades with ``pnl_dollars`` populated.

        Returns
        -------
        dict
            Win-rate percentages and trade counts per category.
        """
        closed = [t for t in trades if t.pnl_dollars is not None]

        if not closed:
            return {
                "chart_type": "win_rate_breakdown",
                "by_scan_type": [],
                "by_time_zone": [],
                "by_session_type": [],
                "overall": {"win_rate": 0.0, "total": 0, "wins": 0, "losses": 0},
            }

        # Overall stats
        wins = [t for t in closed if t.is_winner]
        overall_wr = _safe_div(len(wins), len(closed)) * 100

        def _build_breakdown(
            key_fn,
            label_map: dict[str, str],
        ) -> list[dict[str, Any]]:
            """Group trades by *key_fn* and compute per-group win rate."""
            groups: dict[str, list[TradeLog]] = {}
            for t in closed:
                k = key_fn(t)
                groups.setdefault(k, []).append(t)

            result = []
            for key, group_trades in sorted(groups.items()):
                g_wins = sum(1 for t in group_trades if t.is_winner)
                g_losses = len(group_trades) - g_wins
                wr = _safe_div(g_wins, len(group_trades)) * 100
                avg_pnl = statistics.mean(
                    [t.pnl_dollars for t in group_trades if t.pnl_dollars is not None]
                )
                result.append(
                    {
                        "category": key,
                        "label": label_map.get(key, key),
                        "win_rate": round(wr, 2),
                        "total": len(group_trades),
                        "wins": g_wins,
                        "losses": g_losses,
                        "avg_pnl": round(avg_pnl, 2),
                        "avg_pnl_formatted": format_currency(avg_pnl),
                        "color": color_for_value(wr, 30, 70),
                    }
                )
            return result

        by_scan = _build_breakdown(
            lambda t: t.scan_type.value,
            _SCAN_TYPE_LABELS,
        )
        by_tz = _build_breakdown(
            lambda t: t.time_zone.value,
            _TIME_ZONE_LABELS,
        )
        by_session = _build_breakdown(
            lambda t: t.session_type.value,
            _SESSION_TYPE_LABELS,
        )

        return {
            "chart_type": "win_rate_breakdown",
            "by_scan_type": by_scan,
            "by_time_zone": by_tz,
            "by_session_type": by_session,
            "overall": {
                "win_rate": round(overall_wr, 2),
                "total": len(closed),
                "wins": len(wins),
                "losses": len(closed) - len(wins),
            },
        }

    # -----------------------------------------------------------------
    # 3d) Equity Curve
    # -----------------------------------------------------------------

    @staticmethod
    def equity_curve(daily_pnl: dict[str, float]) -> dict[str, Any]:
        """Multi-day equity curve with rolling Sharpe ratio.

        Parameters
        ----------
        daily_pnl:
            Dictionary keyed by date string (``"YYYY-MM-DD"``) to daily
            net P&L in dollars.  Must be chronologically ordered.

        Returns
        -------
        dict
            Cumulative equity, daily returns, and rolling Sharpe series.
        """
        if not daily_pnl:
            return {
                "chart_type": "equity_curve",
                "dates": [],
                "daily_pnl": [],
                "cumulative_equity": [],
                "rolling_sharpe": [],
            }

        dates = list(daily_pnl.keys())
        daily_values = list(daily_pnl.values())

        cumulative: list[float] = []
        running = 0.0
        for d in daily_values:
            running += d
            cumulative.append(round(running, 2))

        rolling_sharpe = _compute_rolling_sharpe(daily_values, window=20)

        # Compute peak / drawdown for the equity series
        peak = 0.0
        drawdown: list[float] = []
        for eq in cumulative:
            peak = max(peak, eq)
            drawdown.append(round(eq - peak, 2))

        return {
            "chart_type": "equity_curve",
            "dates": dates,
            "daily_pnl": [round(v, 2) for v in daily_values],
            "daily_pnl_formatted": [format_currency(v) for v in daily_values],
            "cumulative_equity": cumulative,
            "drawdown": drawdown,
            "rolling_sharpe": [
                round(s, 4) if s is not None else None for s in rolling_sharpe
            ],
            "total_return": format_currency(cumulative[-1]) if cumulative else "$0.00",
            "max_drawdown": format_currency(min(drawdown)) if drawdown else "$0.00",
            "trading_days": len(dates),
            "colors": {
                "equity_line": "#3b82f6",
                "sharpe_line": "#a855f7",
                "positive_day": "#22c55e",
                "negative_day": "#ef4444",
                "drawdown_fill": "#ef4444",
            },
        }

    # -----------------------------------------------------------------
    # 3e) Drawdown Chart
    # -----------------------------------------------------------------

    @staticmethod
    def drawdown_chart(equity_history: list[float]) -> dict[str, Any]:
        """Drawdown chart showing max drawdown periods.

        Identifies the worst drawdown periods and marks their start/end
        indices for visual emphasis.

        Parameters
        ----------
        equity_history:
            Chronological equity values (e.g. daily ending equity).

        Returns
        -------
        dict
            Drawdown series, max drawdown metadata, and period markers.
        """
        if not equity_history:
            return {
                "chart_type": "drawdown",
                "drawdown_pct": [],
                "drawdown_abs": [],
                "max_drawdown_pct": 0.0,
                "max_drawdown_abs": 0.0,
                "worst_periods": [],
            }

        # Compute drawdown series
        peak = equity_history[0]
        drawdown_abs: list[float] = []
        drawdown_pct: list[float] = []

        for eq in equity_history:
            peak = max(peak, eq)
            dd_abs = eq - peak
            dd_pct = (dd_abs / peak * 100.0) if peak != 0 else 0.0
            drawdown_abs.append(round(dd_abs, 2))
            drawdown_pct.append(round(dd_pct, 4))

        # Identify worst drawdown periods (top 3)
        worst_periods = _find_drawdown_periods(equity_history, top_n=3)

        max_dd_abs = min(drawdown_abs) if drawdown_abs else 0.0
        max_dd_pct = min(drawdown_pct) if drawdown_pct else 0.0

        return {
            "chart_type": "drawdown",
            "drawdown_pct": drawdown_pct,
            "drawdown_abs": drawdown_abs,
            "max_drawdown_pct": round(max_dd_pct, 4),
            "max_drawdown_abs": round(max_dd_abs, 2),
            "max_drawdown_pct_formatted": format_percentage(max_dd_pct),
            "max_drawdown_abs_formatted": format_currency(max_dd_abs),
            "worst_periods": worst_periods,
            "total_points": len(equity_history),
            "colors": {
                "drawdown_fill": "#ef4444",
                "recovery_line": "#22c55e",
                "worst_period_highlight": "#dc2626",
            },
        }

    # -----------------------------------------------------------------
    # 3f) Risk Metrics Cards
    # -----------------------------------------------------------------

    @staticmethod
    def risk_metrics_cards(trades: list[TradeLog]) -> dict[str, Any]:
        """Key risk metrics for dashboard KPI cards.

        Computes Sharpe, Sortino, max drawdown, profit factor, average
        win/loss, expectancy, and other risk-adjusted metrics.

        Parameters
        ----------
        trades:
            Closed trades with ``pnl_dollars`` populated.

        Returns
        -------
        dict
            Dictionary of metric cards, each with value, formatted
            string, colour coding, and description.
        """
        pnl_values = [
            t.pnl_dollars for t in trades if t.pnl_dollars is not None
        ]

        if not pnl_values:
            return {
                "chart_type": "risk_metrics",
                "cards": [],
                "summary": {"total_trades": 0},
            }

        wins = [p for p in pnl_values if p > 0]
        losses = [p for p in pnl_values if p <= 0]
        total_trades = len(pnl_values)

        # Core statistics
        total_pnl = sum(pnl_values)
        win_rate = _safe_div(len(wins), total_trades) * 100
        avg_win = statistics.mean(wins) if wins else 0.0
        avg_loss = statistics.mean(losses) if losses else 0.0
        largest_win = max(wins) if wins else 0.0
        largest_loss = min(losses) if losses else 0.0
        mean_pnl = statistics.mean(pnl_values)
        stdev_pnl = statistics.stdev(pnl_values) if len(pnl_values) > 1 else 0.0

        # Profit factor
        gross_profit = sum(wins) if wins else 0.0
        gross_loss = abs(sum(losses)) if losses else 0.0
        profit_factor = _safe_div(gross_profit, gross_loss, default=float("inf"))

        # Sharpe ratio (annualised, assuming daily trades)
        sharpe = (
            round((mean_pnl / stdev_pnl) * math.sqrt(252), 4)
            if stdev_pnl > 0
            else 0.0
        )

        # Sortino ratio (downside deviation only)
        downside_returns = [p for p in pnl_values if p < 0]
        downside_dev = (
            math.sqrt(statistics.mean([r ** 2 for r in downside_returns]))
            if downside_returns
            else 0.0
        )
        sortino = (
            round((mean_pnl / downside_dev) * math.sqrt(252), 4)
            if downside_dev > 0
            else 0.0
        )

        # Max drawdown from the P&L sequence
        cumulative = []
        running = 0.0
        for p in pnl_values:
            running += p
            cumulative.append(running)
        peak = 0.0
        max_dd = 0.0
        for c in cumulative:
            peak = max(peak, c)
            dd = c - peak
            max_dd = min(max_dd, dd)

        # Expectancy = avg win * win rate - avg loss * loss rate
        loss_rate = 1.0 - (win_rate / 100.0)
        expectancy = (avg_win * win_rate / 100.0) + (avg_loss * loss_rate)

        # Average hold time
        hold_times = [
            t.hold_time_minutes for t in trades
            if t.hold_time_minutes is not None
        ]
        avg_hold = statistics.mean(hold_times) if hold_times else 0.0

        # Payoff ratio
        payoff_ratio = _safe_div(avg_win, abs(avg_loss)) if avg_loss != 0 else 0.0

        cards = [
            _metric_card(
                "Total P&L", total_pnl, format_currency(total_pnl),
                "Net profit/loss across all trades",
                _pnl_color(total_pnl),
            ),
            _metric_card(
                "Win Rate", win_rate, format_percentage(win_rate),
                f"{len(wins)}W / {len(losses)}L of {total_trades} trades",
                color_for_value(win_rate, 30, 70),
            ),
            _metric_card(
                "Sharpe Ratio", sharpe, f"{sharpe:.2f}",
                "Annualised risk-adjusted return",
                color_for_value(sharpe, -1, 3),
            ),
            _metric_card(
                "Sortino Ratio", sortino, f"{sortino:.2f}",
                "Annualised downside risk-adjusted return",
                color_for_value(sortino, -1, 3),
            ),
            _metric_card(
                "Max Drawdown", max_dd, format_currency(max_dd),
                "Largest peak-to-trough decline",
                "#ef4444" if max_dd < 0 else "#22c55e",
            ),
            _metric_card(
                "Profit Factor", profit_factor,
                f"{profit_factor:.2f}" if profit_factor != float("inf") else "N/A",
                "Gross profit / gross loss",
                color_for_value(
                    min(profit_factor, 5), 0.5, 3.0
                ) if profit_factor != float("inf") else "#22c55e",
            ),
            _metric_card(
                "Avg Win", avg_win, format_currency(avg_win),
                f"Average winning trade ({len(wins)} wins)",
                "#22c55e",
            ),
            _metric_card(
                "Avg Loss", avg_loss, format_currency(avg_loss),
                f"Average losing trade ({len(losses)} losses)",
                "#ef4444",
            ),
            _metric_card(
                "Largest Win", largest_win, format_currency(largest_win),
                "Best single trade",
                "#22c55e",
            ),
            _metric_card(
                "Largest Loss", largest_loss, format_currency(largest_loss),
                "Worst single trade",
                "#ef4444",
            ),
            _metric_card(
                "Expectancy", expectancy, format_currency(expectancy),
                "Expected value per trade",
                _pnl_color(expectancy),
            ),
            _metric_card(
                "Payoff Ratio", payoff_ratio, f"{payoff_ratio:.2f}",
                "Avg win / avg loss magnitude",
                color_for_value(payoff_ratio, 0.5, 3.0),
            ),
            _metric_card(
                "Avg Hold Time", avg_hold, f"{avg_hold:.1f} min",
                "Average trade duration in minutes",
                "#3b82f6",
            ),
            _metric_card(
                "Total Trades", float(total_trades), str(total_trades),
                "Number of completed trades",
                "#3b82f6",
            ),
        ]

        return {
            "chart_type": "risk_metrics",
            "cards": cards,
            "summary": {
                "total_trades": total_trades,
                "total_pnl": round(total_pnl, 2),
                "win_rate": round(win_rate, 2),
                "sharpe": sharpe,
                "sortino": sortino,
                "max_drawdown": round(max_dd, 2),
                "profit_factor": (
                    round(profit_factor, 4)
                    if profit_factor != float("inf")
                    else None
                ),
            },
        }


# =============================================================================
# 4. CALIBRATION VISUALIZATION
# =============================================================================


class CalibrationVisualization:
    """Prepares calibration data for frontend rendering.

    Visualises the self-learning pipeline's evolution of weights,
    thresholds, and market regime classifications over time.
    """

    # -----------------------------------------------------------------
    # 4a) Weight Evolution
    # -----------------------------------------------------------------

    @staticmethod
    def weight_evolution(weight_history: list[FactorWeights]) -> dict[str, Any]:
        """Factor weight changes over time.

        Produces a multi-line chart (one line per factor) showing how
        the calibration pipeline has adjusted weights.

        Parameters
        ----------
        weight_history:
            Chronologically ordered list of factor weight snapshots.

        Returns
        -------
        dict
            Series data for each factor weight.
        """
        if not weight_history:
            return {
                "chart_type": "weight_evolution",
                "labels": [],
                "series": [],
                "data_points": 0,
            }

        labels = [f"Cycle {i + 1}" for i in range(len(weight_history))]

        market_internals: list[float] = []
        options_flow: list[float] = []
        price_action: list[float] = []
        gex_structure: list[float] = []
        cross_asset: list[float] = []

        for fw in weight_history:
            market_internals.append(round(fw.market_internals, 4))
            options_flow.append(round(fw.options_flow, 4))
            price_action.append(round(fw.price_action, 4))
            gex_structure.append(round(fw.gex_structure, 4))
            cross_asset.append(round(fw.cross_asset, 4))

        series = [
            {
                "name": "Market Internals",
                "key": "market_internals",
                "data": market_internals,
                "color": "#3b82f6",
            },
            {
                "name": "Options Flow",
                "key": "options_flow",
                "data": options_flow,
                "color": "#22c55e",
            },
            {
                "name": "Price Action",
                "key": "price_action",
                "data": price_action,
                "color": "#f59e0b",
            },
            {
                "name": "GEX Structure",
                "key": "gex_structure",
                "data": gex_structure,
                "color": "#a855f7",
            },
            {
                "name": "Cross-Asset",
                "key": "cross_asset",
                "data": cross_asset,
                "color": "#06b6d4",
            },
        ]

        # Compute deltas (change from first to last snapshot)
        if len(weight_history) >= 2:
            first = weight_history[0]
            last = weight_history[-1]
            deltas = {
                "market_internals": round(last.market_internals - first.market_internals, 4),
                "options_flow": round(last.options_flow - first.options_flow, 4),
                "price_action": round(last.price_action - first.price_action, 4),
                "gex_structure": round(last.gex_structure - first.gex_structure, 4),
                "cross_asset": round(last.cross_asset - first.cross_asset, 4),
            }
        else:
            deltas = {}

        return {
            "chart_type": "weight_evolution",
            "labels": labels,
            "series": series,
            "deltas": deltas,
            "data_points": len(weight_history),
            "current_weights": weight_history[-1].as_dict() if weight_history else {},
        }

    # -----------------------------------------------------------------
    # 4b) Threshold Evolution
    # -----------------------------------------------------------------

    @staticmethod
    def threshold_evolution(
        threshold_history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Entry threshold changes over calibration cycles.

        Parameters
        ----------
        threshold_history:
            List of dicts, each containing at minimum:
            ``{"timestamp": datetime, "entry_threshold": float}``.
            May also include ``stop_loss_pct`` and per-zone profit
            targets.

        Returns
        -------
        dict
            Time series of threshold values.
        """
        if not threshold_history:
            return {
                "chart_type": "threshold_evolution",
                "labels": [],
                "entry_threshold": [],
                "stop_loss_pct": [],
                "profit_targets": {},
                "data_points": 0,
            }

        labels: list[str] = []
        entry_thresholds: list[float] = []
        stop_losses: list[float] = []
        profit_targets_by_zone: dict[str, list[float]] = {}

        for idx, th in enumerate(threshold_history):
            ts = th.get("timestamp")
            if isinstance(ts, datetime):
                labels.append(_iso(ts))
            else:
                labels.append(f"Cycle {idx + 1}")

            entry_thresholds.append(round(th.get("entry_threshold", 0.0), 4))
            stop_losses.append(round(th.get("stop_loss_pct", 0.0), 4))

            targets = th.get("profit_targets_by_zone", {})
            for zone, val in targets.items():
                if zone not in profit_targets_by_zone:
                    profit_targets_by_zone[zone] = []
                profit_targets_by_zone[zone].append(round(val, 4))

        return {
            "chart_type": "threshold_evolution",
            "labels": labels,
            "entry_threshold": entry_thresholds,
            "stop_loss_pct": stop_losses,
            "profit_targets": {
                zone: vals for zone, vals in profit_targets_by_zone.items()
            },
            "data_points": len(threshold_history),
            "current": {
                "entry_threshold": entry_thresholds[-1] if entry_thresholds else None,
                "stop_loss_pct": stop_losses[-1] if stop_losses else None,
            },
            "colors": {
                "entry_threshold": "#3b82f6",
                "stop_loss_pct": "#ef4444",
                "profit_targets": "#22c55e",
            },
        }

    # -----------------------------------------------------------------
    # 4c) Regime Timeline
    # -----------------------------------------------------------------

    @staticmethod
    def regime_timeline(
        regime_history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Market regime classification over time.

        Parameters
        ----------
        regime_history:
            List of dicts with ``{"timestamp": datetime, "regime": str}``.
            May also include ``"vix"`` and ``"total_net_gex"`` fields.

        Returns
        -------
        dict
            Timeline of regime labels with colours and supplemental
            metrics.
        """
        regime_colors = {
            "LOW": "#22c55e",
            "NORMAL": "#3b82f6",
            "ELEVATED": "#f59e0b",
            "EXTREME": "#ef4444",
        }

        if not regime_history:
            return {
                "chart_type": "regime_timeline",
                "timestamps": [],
                "regimes": [],
                "vix": [],
                "gex": [],
                "colors": regime_colors,
            }

        timestamps: list[str] = []
        regimes: list[str] = []
        regime_color_series: list[str] = []
        vix_values: list[Optional[float]] = []
        gex_values: list[Optional[float]] = []

        for entry in regime_history:
            ts = entry.get("timestamp")
            if isinstance(ts, datetime):
                timestamps.append(_iso(ts))
            else:
                timestamps.append(str(ts))

            regime = str(entry.get("regime", "UNKNOWN"))
            regimes.append(regime)
            regime_color_series.append(
                regime_colors.get(regime, "#64748b")
            )
            vix_values.append(entry.get("vix"))
            gex_values.append(entry.get("total_net_gex"))

        # Count time spent in each regime
        regime_counts: dict[str, int] = {}
        for r in regimes:
            regime_counts[r] = regime_counts.get(r, 0) + 1

        return {
            "chart_type": "regime_timeline",
            "timestamps": timestamps,
            "regimes": regimes,
            "regime_colors": regime_color_series,
            "vix": vix_values,
            "gex": gex_values,
            "regime_counts": regime_counts,
            "colors": regime_colors,
        }

    # -----------------------------------------------------------------
    # 4d) GEX Accuracy Chart
    # -----------------------------------------------------------------

    @staticmethod
    def gex_accuracy_chart(
        accuracy_history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """GEX signal accuracy over rolling window.

        Parameters
        ----------
        accuracy_history:
            List of dicts with ``{"timestamp": datetime, "accuracy": float}``.
            May also include ``"signal_count"`` and ``"signal_type"`` fields.

        Returns
        -------
        dict
            Time series of GEX accuracy with aggregate statistics.
        """
        if not accuracy_history:
            return {
                "chart_type": "gex_accuracy",
                "timestamps": [],
                "accuracy": [],
                "signal_counts": [],
                "avg_accuracy": 0.0,
                "data_points": 0,
            }

        timestamps: list[str] = []
        accuracy: list[float] = []
        signal_counts: list[int] = []
        by_signal_type: dict[str, list[float]] = {}

        for entry in accuracy_history:
            ts = entry.get("timestamp")
            if isinstance(ts, datetime):
                timestamps.append(_iso(ts))
            else:
                timestamps.append(str(ts))

            acc = float(entry.get("accuracy", 0.0))
            accuracy.append(round(acc, 4))
            signal_counts.append(int(entry.get("signal_count", 0)))

            sig_type = entry.get("signal_type")
            if sig_type:
                by_signal_type.setdefault(str(sig_type), []).append(round(acc, 4))

        avg_accuracy = statistics.mean(accuracy) if accuracy else 0.0

        # Per-signal-type averages
        type_averages: dict[str, float] = {}
        for sig_type, acc_list in by_signal_type.items():
            type_averages[sig_type] = round(statistics.mean(acc_list), 4)

        return {
            "chart_type": "gex_accuracy",
            "timestamps": timestamps,
            "accuracy": accuracy,
            "signal_counts": signal_counts,
            "avg_accuracy": round(avg_accuracy, 4),
            "avg_accuracy_formatted": format_percentage(avg_accuracy * 100),
            "by_signal_type": type_averages,
            "data_points": len(accuracy_history),
            "threshold_line": 0.6,
            "colors": {
                "accuracy_line": "#3b82f6",
                "threshold": "#ef4444",
                "above_threshold": "#22c55e",
                "below_threshold": "#ef4444",
            },
        }


# =============================================================================
# INTERNAL UTILITY FUNCTIONS
# =============================================================================


def _metric_card(
    name: str,
    value: float,
    formatted: str,
    description: str,
    color: str,
) -> dict[str, Any]:
    """Build a single metric card dictionary."""
    return {
        "name": name,
        "value": round(value, 4),
        "formatted": formatted,
        "description": description,
        "color": color,
    }


def _pnl_color(value: float) -> str:
    """Return green for positive P&L, red for negative, slate for zero."""
    if value > 0:
        return "#22c55e"
    elif value < 0:
        return "#ef4444"
    return "#64748b"


def _count_by_key(items: list[dict], key: str) -> dict[str, int]:
    """Count occurrences of each value for *key* in a list of dicts."""
    counts: dict[str, int] = {}
    for item in items:
        val = str(item.get(key, "UNKNOWN"))
        counts[val] = counts.get(val, 0) + 1
    return counts


def _percentile(sorted_data: list[float], pct: float) -> float:
    """Compute the *pct*-th percentile of *sorted_data* (already sorted).

    Uses linear interpolation between adjacent elements.
    """
    if not sorted_data:
        return 0.0
    if len(sorted_data) == 1:
        return sorted_data[0]

    k = (pct / 100.0) * (len(sorted_data) - 1)
    f = math.floor(k)
    c = math.ceil(k)

    if f == c:
        return sorted_data[int(k)]

    lower = sorted_data[int(f)]
    upper = sorted_data[int(c)]
    return lower + (upper - lower) * (k - f)


def _compute_skewness(values: list[float]) -> float:
    """Compute the sample skewness of a list of values.

    Returns 0.0 if insufficient data or zero variance.
    """
    n = len(values)
    if n < 3:
        return 0.0

    mean = statistics.mean(values)
    std = statistics.stdev(values)
    if std == 0:
        return 0.0

    m3 = sum((x - mean) ** 3 for x in values) / n
    return m3 / (std ** 3)


def _find_drawdown_periods(
    equity: list[float],
    top_n: int = 3,
) -> list[dict[str, Any]]:
    """Identify the worst *top_n* drawdown periods in an equity series.

    A drawdown period begins when equity falls below a prior peak and
    ends when a new peak is reached (or at the end of the series).

    Parameters
    ----------
    equity:
        Chronological equity values.
    top_n:
        Number of worst periods to return.

    Returns
    -------
    list[dict]
        Each dict contains ``start_idx``, ``trough_idx``, ``end_idx``,
        ``drawdown_abs``, and ``drawdown_pct``.
    """
    if len(equity) < 2:
        return []

    periods: list[dict[str, Any]] = []
    peak = equity[0]
    peak_idx = 0
    trough = equity[0]
    trough_idx = 0
    in_drawdown = False
    dd_start = 0

    for i in range(1, len(equity)):
        if equity[i] >= peak:
            if in_drawdown:
                # Drawdown period ends -- record it
                dd_abs = trough - equity[dd_start]
                dd_pct = (
                    (dd_abs / equity[dd_start] * 100.0) if equity[dd_start] != 0 else 0.0
                )
                periods.append(
                    {
                        "start_idx": dd_start,
                        "trough_idx": trough_idx,
                        "end_idx": i,
                        "drawdown_abs": round(dd_abs, 2),
                        "drawdown_pct": round(dd_pct, 4),
                        "duration": i - dd_start,
                    }
                )
                in_drawdown = False
            peak = equity[i]
            peak_idx = i
            trough = equity[i]
            trough_idx = i
        else:
            if not in_drawdown:
                in_drawdown = True
                dd_start = peak_idx
            if equity[i] < trough:
                trough = equity[i]
                trough_idx = i

    # Handle ongoing drawdown at end of series
    if in_drawdown:
        dd_abs = trough - equity[dd_start]
        dd_pct = (dd_abs / equity[dd_start] * 100.0) if equity[dd_start] != 0 else 0.0
        periods.append(
            {
                "start_idx": dd_start,
                "trough_idx": trough_idx,
                "end_idx": len(equity) - 1,
                "drawdown_abs": round(dd_abs, 2),
                "drawdown_pct": round(dd_pct, 4),
                "duration": len(equity) - 1 - dd_start,
                "ongoing": True,
            }
        )

    # Sort by drawdown magnitude (most negative first) and return top N
    periods.sort(key=lambda p: p["drawdown_abs"])
    return periods[:top_n]
