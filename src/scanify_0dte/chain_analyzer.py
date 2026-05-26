"""
SCANIFY SPX 0DTE Scanner -- Options Chain Deep Analysis Engine
===============================================================

Provides deep analysis of the SPX 0DTE options chain including:
    - Put/call ratio computation (volume, OI, premium-weighted)
    - Implied volatility skew analysis (risk reversal, slope, convexity)
    - Volatility term structure across multiple expiries
    - Unusual activity detection (volume spikes, block trades, sweeps)
    - Options flow classification (bullish/bearish/neutral with confidence)
    - Max pain calculation with sensitivity analysis
    - Dealer exposure summary (delta, gamma, vanna, charm)
    - Open interest profile and clustering
    - Intraday volume profile and weighted average strike
    - Hedging cluster identification

Depends on
----------
- ``models``    : OptionsChain, OptionQuote, OptionSide
- ``constants`` : SPX_CONTRACT (MULTIPLIER), GEX_SCANNER

References
----------
- Cboe Options Exchange -- Put/Call Ratio methodology
- Natenberg (1994), *Option Volatility and Pricing*
- Sinclair (2013), *Volatility Trading*, Ch. 7 -- Skew Dynamics
- SqueezeMetrics GEX / dealer positioning framework
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .constants import SPX_CONTRACT, TRADING_DAYS_PER_YEAR
from .models import OptionsChain, OptionQuote, OptionSide

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------

_CONTRACT_MULTIPLIER: float = SPX_CONTRACT.multiplier  # 100
_ES_MULTIPLIER: float = 50.0  # E-mini S&P 500 point value
_EPSILON: float = 1e-12  # Division-by-zero guard

# Unusual activity thresholds
_VOLUME_OI_RATIO_ALERT: float = 3.0  # Volume > 3x OI
_BLOCK_TRADE_THRESHOLD: int = 100  # Contracts
_OI_CHANGE_MULTIPLIER: float = 2.0  # OI change > 2x typical
_SWEEP_TIME_WINDOW_SECONDS: int = 2  # Max time between legs of a sweep

# Flow classification
_HIGH_CONFIDENCE_THRESHOLD: float = 0.70
_MODERATE_CONFIDENCE_THRESHOLD: float = 0.50

# Max pain iteration
_MAX_PAIN_SEARCH_MARGIN_PCT: float = 0.10  # Search +/-10% around spot

# Historical skew defaults (25-delta risk reversal, annualised)
_DEFAULT_HISTORICAL_SKEW_RR: float = 0.04  # 4 vol points put skew typical for SPX
_DEFAULT_HISTORICAL_SKEW_SLOPE: float = 0.015  # 1.5 vol points per 1% OTM


def _safe_divide(numerator: float, denominator: float) -> float:
    """Return *numerator / denominator*, or 0.0 when *denominator* ~ 0."""
    if abs(denominator) < _EPSILON:
        return 0.0
    return numerator / denominator


def _interpolate_delta_strike(
    quotes: list[OptionQuote],
    target_delta: float,
) -> Optional[OptionQuote]:
    """Find the quote whose absolute delta is closest to *target_delta*.

    Parameters
    ----------
    quotes : list[OptionQuote]
        Sorted list of quotes (calls or puts) for one side.
    target_delta : float
        Absolute delta target (e.g. 0.25 for 25-delta).

    Returns
    -------
    OptionQuote or None
        The quote with the closest absolute delta match, or None if
        *quotes* is empty.
    """
    if not quotes:
        return None
    return min(quotes, key=lambda q: abs(abs(q.delta) - target_delta))


# =========================================================================
# 1. ChainAnalyzer
# =========================================================================


class ChainAnalyzer:
    """Deep analysis of 0DTE SPX options chain.

    Provides a comprehensive suite of analytical methods that consume an
    ``OptionsChain`` snapshot and return structured dictionaries of metrics.
    All methods are stateless and can be called independently.

    Usage::

        analyzer = ChainAnalyzer()
        pc_ratio = analyzer.compute_put_call_ratio(chain)
        skew = analyzer.compute_iv_skew(chain, spot=5250.0)
    """

    # -----------------------------------------------------------------
    # a) Put / Call Ratio
    # -----------------------------------------------------------------

    def compute_put_call_ratio(self, chain: OptionsChain) -> dict:
        """Compute put/call ratio three ways with interpretation.

        Parameters
        ----------
        chain : OptionsChain
            Current options chain snapshot.

        Returns
        -------
        dict
            Keys:
            - ``volume_pc_ratio`` : float -- total put volume / total call volume.
            - ``oi_pc_ratio`` : float -- total put OI / total call OI.
            - ``premium_pc_ratio`` : float -- put premium dollars / call premium dollars.
            - ``call_volume`` : int
            - ``put_volume`` : int
            - ``call_oi`` : int
            - ``put_oi`` : int
            - ``call_premium`` : float -- aggregate call premium ($).
            - ``put_premium`` : float -- aggregate put premium ($).
            - ``interpretation`` : str -- human-readable summary.
        """
        calls = chain.calls
        puts = chain.puts

        call_volume = sum(q.volume for q in calls)
        put_volume = sum(q.volume for q in puts)
        call_oi = sum(q.open_interest for q in calls)
        put_oi = sum(q.open_interest for q in puts)

        # Premium = mid * volume * multiplier  ($ notional traded)
        call_premium = sum(
            q.mid * q.volume * _CONTRACT_MULTIPLIER for q in calls
        )
        put_premium = sum(
            q.mid * q.volume * _CONTRACT_MULTIPLIER for q in puts
        )

        volume_pc = _safe_divide(float(put_volume), float(call_volume))
        oi_pc = _safe_divide(float(put_oi), float(call_oi))
        premium_pc = _safe_divide(put_premium, call_premium)

        # Interpretation logic
        interpretation = self._interpret_pc_ratio(volume_pc, oi_pc, premium_pc)

        return {
            "volume_pc_ratio": round(volume_pc, 4),
            "oi_pc_ratio": round(oi_pc, 4),
            "premium_pc_ratio": round(premium_pc, 4),
            "call_volume": call_volume,
            "put_volume": put_volume,
            "call_oi": call_oi,
            "put_oi": put_oi,
            "call_premium": round(call_premium, 2),
            "put_premium": round(put_premium, 2),
            "interpretation": interpretation,
        }

    @staticmethod
    def _interpret_pc_ratio(
        volume_pc: float,
        oi_pc: float,
        premium_pc: float,
    ) -> str:
        """Produce a human-readable interpretation of the P/C ratios."""
        signals: list[str] = []
        bullish_count = 0
        bearish_count = 0

        for label, ratio in [
            ("Volume P/C", volume_pc),
            ("OI P/C", oi_pc),
            ("Premium P/C", premium_pc),
        ]:
            if ratio > 1.2:
                signals.append(f"{label} elevated ({ratio:.2f}) -- bearish sentiment")
                bearish_count += 1
            elif ratio < 0.7:
                signals.append(f"{label} depressed ({ratio:.2f}) -- bullish sentiment")
                bullish_count += 1
            else:
                signals.append(f"{label} neutral ({ratio:.2f})")

        if bearish_count >= 2:
            summary = "BEARISH: Elevated put activity across multiple measures."
        elif bullish_count >= 2:
            summary = "BULLISH: Depressed put activity suggests call-heavy positioning."
        else:
            summary = "NEUTRAL: Mixed or balanced put/call activity."

        return f"{summary} | {' | '.join(signals)}"

    # -----------------------------------------------------------------
    # b) IV Skew Analysis
    # -----------------------------------------------------------------

    def compute_iv_skew(
        self,
        chain: OptionsChain,
        spot: float,
        historical_avg_rr: float = _DEFAULT_HISTORICAL_SKEW_RR,
        historical_avg_slope: float = _DEFAULT_HISTORICAL_SKEW_SLOPE,
    ) -> dict:
        """Analyze implied volatility skew.

        Parameters
        ----------
        chain : OptionsChain
            Current options chain snapshot.
        spot : float
            Current SPX spot price.
        historical_avg_rr : float
            Historical average 25-delta risk reversal (put IV - call IV).
        historical_avg_slope : float
            Historical average skew slope (IV per 1% OTM).

        Returns
        -------
        dict
            - ``atm_iv`` : float -- ATM implied volatility.
            - ``put_25d_iv`` : float -- 25-delta put IV.
            - ``call_25d_iv`` : float -- 25-delta call IV.
            - ``risk_reversal_25d`` : float -- put_25d_iv - call_25d_iv.
            - ``skew_slope`` : float -- IV change per 1% OTM.
            - ``skew_convexity`` : float -- curvature of the skew.
            - ``rr_vs_historical`` : float -- current RR minus historical avg.
            - ``slope_vs_historical`` : float -- current slope minus historical avg.
            - ``skew_interpretation`` : str -- human-readable summary.
        """
        calls = chain.calls
        puts = chain.puts

        # ATM IV: average of ATM call and put IV
        atm_strike = chain.atm_strike()
        atm_quotes = chain.get_by_strike(atm_strike)
        atm_ivs = [q.implied_vol for q in atm_quotes if q.implied_vol > 0]
        atm_iv = float(np.mean(atm_ivs)) if atm_ivs else 0.0

        # 25-delta quotes
        put_25d = _interpolate_delta_strike(puts, 0.25)
        call_25d = _interpolate_delta_strike(calls, 0.25)

        put_25d_iv = put_25d.implied_vol if put_25d else atm_iv
        call_25d_iv = call_25d.implied_vol if call_25d else atm_iv

        risk_reversal = put_25d_iv - call_25d_iv

        # Skew slope: compute linear fit of IV vs moneyness for puts
        skew_slope, skew_convexity = self._compute_skew_shape(puts, spot)

        # Compare to historical
        rr_vs_hist = risk_reversal - historical_avg_rr
        slope_vs_hist = skew_slope - historical_avg_slope

        # Interpretation
        interpretation = self._interpret_skew(
            risk_reversal, skew_slope, rr_vs_hist, slope_vs_hist
        )

        return {
            "atm_iv": round(atm_iv, 6),
            "put_25d_iv": round(put_25d_iv, 6),
            "call_25d_iv": round(call_25d_iv, 6),
            "risk_reversal_25d": round(risk_reversal, 6),
            "skew_slope": round(skew_slope, 6),
            "skew_convexity": round(skew_convexity, 6),
            "rr_vs_historical": round(rr_vs_hist, 6),
            "slope_vs_historical": round(slope_vs_hist, 6),
            "skew_interpretation": interpretation,
        }

    def _compute_skew_shape(
        self,
        puts: list[OptionQuote],
        spot: float,
    ) -> Tuple[float, float]:
        """Fit IV skew slope and convexity from put quotes.

        Uses OTM puts to measure IV as a function of moneyness
        (strike / spot). Fits a second-order polynomial to extract
        the linear slope and quadratic curvature.

        Returns
        -------
        tuple[float, float]
            (slope, convexity) where slope is IV per 1% OTM and
            convexity is the second-order coefficient.
        """
        if len(puts) < 3 or spot <= 0:
            return 0.0, 0.0

        # Filter to OTM puts with valid IV
        otm_puts = [
            q for q in puts
            if q.strike < spot and q.implied_vol > 0
        ]
        if len(otm_puts) < 3:
            return 0.0, 0.0

        # Moneyness: percentage distance from spot  (negative for OTM puts)
        moneyness = np.array([(q.strike / spot - 1.0) * 100.0 for q in otm_puts])
        ivs = np.array([q.implied_vol for q in otm_puts])

        try:
            # Quadratic fit: IV = a * m^2 + b * m + c
            coeffs = np.polyfit(moneyness, ivs, deg=2)
            convexity = float(coeffs[0])  # Second-order (curvature)
            slope = float(coeffs[1])  # First-order (slope per 1% OTM)
        except (np.linalg.LinAlgError, ValueError):
            logger.warning("Skew polyfit failed; returning zero slope/convexity.")
            slope, convexity = 0.0, 0.0

        return slope, convexity

    @staticmethod
    def _interpret_skew(
        rr: float,
        slope: float,
        rr_vs_hist: float,
        slope_vs_hist: float,
    ) -> str:
        """Human-readable skew interpretation."""
        parts: list[str] = []

        # Risk reversal
        if rr > 0.06:
            parts.append("Steep put skew -- strong demand for downside protection")
        elif rr > 0.03:
            parts.append("Moderate put skew -- normal hedging demand")
        elif rr > 0:
            parts.append("Mild put skew -- balanced positioning")
        else:
            parts.append("Inverted skew -- unusual call demand exceeding puts")

        # Relative to history
        if rr_vs_hist > 0.02:
            parts.append("skew RICHER than historical average")
        elif rr_vs_hist < -0.02:
            parts.append("skew CHEAPER than historical average")
        else:
            parts.append("skew near historical average")

        # Slope
        if abs(slope_vs_hist) > 0.005:
            direction = "steeper" if slope_vs_hist > 0 else "flatter"
            parts.append(f"slope {direction} than average")

        return " | ".join(parts)

    # -----------------------------------------------------------------
    # c) Volatility Term Structure
    # -----------------------------------------------------------------

    def compute_term_structure(
        self,
        chains: dict[str, OptionsChain],
    ) -> dict:
        """Compute ATM IV term structure across multiple expiries.

        Parameters
        ----------
        chains : dict[str, OptionsChain]
            Mapping of expiry label (e.g. ``"0DTE"``, ``"1DTE"``) to
            the corresponding ``OptionsChain``.

        Returns
        -------
        dict
            - ``atm_iv_by_expiry`` : dict[str, float]
            - ``is_contango`` : bool -- True if ATM IV increases with DTE.
            - ``is_backwardation`` : bool -- True if ATM IV decreases with DTE.
            - ``term_structure_slope`` : float -- IV change per day.
            - ``classification`` : str -- ``"CONTANGO"`` / ``"BACKWARDATION"``
              / ``"FLAT"`` / ``"HUMPED"``.
        """
        atm_ivs: dict[str, float] = {}
        expiry_dte: list[Tuple[float, float]] = []  # (days_to_expiry, iv)

        for label, chain in chains.items():
            atm_strike = chain.atm_strike()
            atm_quotes = chain.get_by_strike(atm_strike)
            ivs = [q.implied_vol for q in atm_quotes if q.implied_vol > 0]
            if not ivs:
                continue

            avg_iv = float(np.mean(ivs))
            atm_ivs[label] = round(avg_iv, 6)

            # Estimate DTE from expiry_date
            dte = (chain.expiry_date - chain.timestamp.date()).days
            dte = max(dte, 0)
            expiry_dte.append((float(dte), avg_iv))

        # Sort by DTE
        expiry_dte.sort(key=lambda x: x[0])

        # Classify term structure
        classification = "FLAT"
        is_contango = False
        is_backwardation = False
        ts_slope = 0.0

        if len(expiry_dte) >= 2:
            dtes = np.array([e[0] for e in expiry_dte])
            ivs_arr = np.array([e[1] for e in expiry_dte])

            # Simple linear regression for slope
            if len(dtes) >= 2 and (dtes[-1] - dtes[0]) > 0:
                try:
                    coeffs = np.polyfit(dtes, ivs_arr, deg=1)
                    ts_slope = float(coeffs[0])
                except (np.linalg.LinAlgError, ValueError):
                    ts_slope = 0.0

            if ts_slope > 0.001:
                classification = "CONTANGO"
                is_contango = True
            elif ts_slope < -0.001:
                classification = "BACKWARDATION"
                is_backwardation = True
            else:
                # Check for humped structure (middle higher than ends)
                if len(ivs_arr) >= 3:
                    mid_idx = len(ivs_arr) // 2
                    if (
                        ivs_arr[mid_idx] > ivs_arr[0]
                        and ivs_arr[mid_idx] > ivs_arr[-1]
                    ):
                        classification = "HUMPED"
                    else:
                        classification = "FLAT"

        return {
            "atm_iv_by_expiry": atm_ivs,
            "is_contango": is_contango,
            "is_backwardation": is_backwardation,
            "term_structure_slope": round(ts_slope, 6),
            "classification": classification,
        }

    # -----------------------------------------------------------------
    # d) Unusual Activity Detection
    # -----------------------------------------------------------------

    def detect_unusual_activity(
        self,
        chain: OptionsChain,
        historical_avg: dict | None = None,
    ) -> list[dict]:
        """Detect unusual options activity in the chain.

        Parameters
        ----------
        chain : OptionsChain
            Current options chain snapshot.
        historical_avg : dict, optional
            Mapping of ``strike -> {"avg_volume": float, "avg_oi": float}``
            for baseline comparison. When ``None``, uses OI as volume baseline.

        Returns
        -------
        list[dict]
            Each alert dict contains:
            - ``strike`` : float
            - ``option_type`` : str (``"CALL"`` or ``"PUT"``)
            - ``alert_type`` : str
            - ``severity`` : str (``"LOW"`` / ``"MEDIUM"`` / ``"HIGH"``)
            - ``volume`` : int
            - ``open_interest`` : int
            - ``ratio`` : float -- the triggering ratio.
            - ``description`` : str
        """
        alerts: list[dict] = []

        for quote in chain.quotes:
            strike = quote.strike
            otype = quote.option_type.value

            # --- Volume vs OI spike ---
            if quote.open_interest > 0:
                vol_oi_ratio = quote.volume / float(quote.open_interest)
                if vol_oi_ratio >= _VOLUME_OI_RATIO_ALERT:
                    severity = self._volume_severity(vol_oi_ratio)
                    alerts.append({
                        "strike": strike,
                        "option_type": otype,
                        "alert_type": "VOLUME_SPIKE",
                        "severity": severity,
                        "volume": quote.volume,
                        "open_interest": quote.open_interest,
                        "ratio": round(vol_oi_ratio, 2),
                        "description": (
                            f"{otype} {strike}: volume {quote.volume} is "
                            f"{vol_oi_ratio:.1f}x open interest {quote.open_interest}"
                        ),
                    })

            # --- Historical comparison ---
            if historical_avg is not None:
                hist = historical_avg.get(strike)
                if hist is not None:
                    avg_vol = hist.get("avg_volume", 0.0)
                    avg_oi = hist.get("avg_oi", 0.0)

                    if avg_vol > 0 and quote.volume > avg_vol * _VOLUME_OI_RATIO_ALERT:
                        ratio = quote.volume / avg_vol
                        alerts.append({
                            "strike": strike,
                            "option_type": otype,
                            "alert_type": "VOLUME_VS_HISTORICAL",
                            "severity": self._volume_severity(ratio),
                            "volume": quote.volume,
                            "open_interest": quote.open_interest,
                            "ratio": round(ratio, 2),
                            "description": (
                                f"{otype} {strike}: volume {quote.volume} is "
                                f"{ratio:.1f}x historical avg {avg_vol:.0f}"
                            ),
                        })

                    if avg_oi > 0 and quote.open_interest > avg_oi * _OI_CHANGE_MULTIPLIER:
                        oi_ratio = quote.open_interest / avg_oi
                        alerts.append({
                            "strike": strike,
                            "option_type": otype,
                            "alert_type": "OI_BUILDUP",
                            "severity": self._volume_severity(oi_ratio),
                            "volume": quote.volume,
                            "open_interest": quote.open_interest,
                            "ratio": round(oi_ratio, 2),
                            "description": (
                                f"{otype} {strike}: OI {quote.open_interest} is "
                                f"{oi_ratio:.1f}x historical avg {avg_oi:.0f}"
                            ),
                        })

            # --- Large block heuristic (volume in a single snapshot suggests blocks) ---
            if quote.volume >= _BLOCK_TRADE_THRESHOLD:
                alerts.append({
                    "strike": strike,
                    "option_type": otype,
                    "alert_type": "LARGE_VOLUME_BLOCK",
                    "severity": "MEDIUM" if quote.volume < 500 else "HIGH",
                    "volume": quote.volume,
                    "open_interest": quote.open_interest,
                    "ratio": round(
                        _safe_divide(float(quote.volume), float(max(quote.open_interest, 1))),
                        2,
                    ),
                    "description": (
                        f"{otype} {strike}: {quote.volume} contracts traded -- "
                        f"potential block activity"
                    ),
                })

        # Deduplicate by (strike, option_type, alert_type)
        seen: set[Tuple[float, str, str]] = set()
        unique_alerts: list[dict] = []
        for alert in alerts:
            key = (alert["strike"], alert["option_type"], alert["alert_type"])
            if key not in seen:
                seen.add(key)
                unique_alerts.append(alert)

        # Sort by severity (HIGH first) then by volume descending
        severity_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        unique_alerts.sort(
            key=lambda a: (severity_order.get(a["severity"], 3), -a["volume"])
        )

        logger.info(
            "Unusual activity scan: %d alerts across %d quotes.",
            len(unique_alerts),
            len(chain.quotes),
        )
        return unique_alerts

    @staticmethod
    def _volume_severity(ratio: float) -> str:
        """Map a volume ratio to a severity label."""
        if ratio >= 10.0:
            return "HIGH"
        elif ratio >= 5.0:
            return "MEDIUM"
        return "LOW"

    # -----------------------------------------------------------------
    # e) Flow Classification
    # -----------------------------------------------------------------

    def classify_flow(
        self,
        chain: OptionsChain,
        trades: list[dict] | None = None,
    ) -> dict:
        """Classify aggregate options flow as bullish, bearish, or neutral.

        Uses both chain-level analysis (volume, OI, premium) and, when
        available, individual trade-level data for more granular
        classification.

        Parameters
        ----------
        chain : OptionsChain
            Current options chain snapshot.
        trades : list[dict], optional
            Individual trade records. Each dict should contain at minimum:
            ``{"strike", "option_type", "size", "price", "side",
            "timestamp"}``.  ``side`` is ``"BUY"`` or ``"SELL"``.

        Returns
        -------
        dict
            - ``direction`` : str -- ``"BULLISH"`` / ``"BEARISH"`` / ``"NEUTRAL"``.
            - ``confidence`` : float -- 0.0 to 1.0.
            - ``call_premium_flow`` : float -- net call premium ($ buy - $ sell).
            - ``put_premium_flow`` : float -- net put premium ($ buy - $ sell).
            - ``net_premium_flow`` : float -- positive = bullish bias.
            - ``block_direction`` : str -- block trade bias.
            - ``sweep_direction`` : str -- sweep bias.
            - ``components`` : dict -- breakdown of contributing signals.
        """
        calls = chain.calls
        puts = chain.puts

        # --- Chain-level flow analysis ---
        call_vol = sum(q.volume for q in calls)
        put_vol = sum(q.volume for q in puts)
        call_premium = sum(q.mid * q.volume * _CONTRACT_MULTIPLIER for q in calls)
        put_premium = sum(q.mid * q.volume * _CONTRACT_MULTIPLIER for q in puts)

        total_premium = call_premium + put_premium
        net_premium = call_premium - put_premium  # positive = call-heavy = bullish

        # Volume skew signal  (-1 bearish, +1 bullish)
        total_vol = call_vol + put_vol
        if total_vol > 0:
            volume_signal = (call_vol - put_vol) / float(total_vol)
        else:
            volume_signal = 0.0

        # Premium skew signal
        if total_premium > 0:
            premium_signal = net_premium / total_premium
        else:
            premium_signal = 0.0

        # --- Trade-level analysis (if available) ---
        trade_flow_signal = 0.0
        block_direction = "NEUTRAL"
        sweep_direction = "NEUTRAL"
        call_flow_net = 0.0
        put_flow_net = 0.0

        if trades:
            classifier = FlowClassifier()
            aggregated = classifier.aggregate_flow(trades)
            trade_flow_signal = aggregated.get("net_signal", 0.0)
            block_direction = aggregated.get("block_direction", "NEUTRAL")
            sweep_direction = aggregated.get("sweep_direction", "NEUTRAL")
            call_flow_net = aggregated.get("call_flow_net", 0.0)
            put_flow_net = aggregated.get("put_flow_net", 0.0)

        # --- Composite signal ---
        # Weight: chain volume/premium = 60%, trade-level = 40%
        if trades:
            composite = 0.3 * volume_signal + 0.3 * premium_signal + 0.4 * trade_flow_signal
        else:
            composite = 0.5 * volume_signal + 0.5 * premium_signal

        # Direction and confidence
        if composite > 0.10:
            direction = "BULLISH"
        elif composite < -0.10:
            direction = "BEARISH"
        else:
            direction = "NEUTRAL"

        confidence = min(abs(composite) / 0.5, 1.0)  # Normalize to [0, 1]

        return {
            "direction": direction,
            "confidence": round(confidence, 4),
            "call_premium_flow": round(call_premium + call_flow_net, 2),
            "put_premium_flow": round(put_premium + put_flow_net, 2),
            "net_premium_flow": round(net_premium + (call_flow_net - put_flow_net), 2),
            "block_direction": block_direction,
            "sweep_direction": sweep_direction,
            "components": {
                "volume_signal": round(volume_signal, 4),
                "premium_signal": round(premium_signal, 4),
                "trade_flow_signal": round(trade_flow_signal, 4),
                "composite_signal": round(composite, 4),
            },
        }

    # -----------------------------------------------------------------
    # f) Max Pain Analysis
    # -----------------------------------------------------------------

    def compute_max_pain(
        self,
        chain: OptionsChain,
        historical_accuracy: float | None = None,
    ) -> dict:
        """Detailed max pain analysis.

        Max pain is the strike price at which the aggregate dollar value
        of all in-the-money options (by open interest) is minimised.

        Parameters
        ----------
        chain : OptionsChain
            Current options chain snapshot.
        historical_accuracy : float, optional
            Historical fraction of sessions where price settled within
            $5 of the max pain strike (0.0--1.0).

        Returns
        -------
        dict
            - ``max_pain_strike`` : float
            - ``max_pain_value`` : float -- aggregate $ pain at the max
              pain strike.
            - ``pain_at_spot`` : float -- aggregate $ pain at the current
              spot.
            - ``pain_sensitivity`` : float -- $ pain change per $1 move
              from max pain.
            - ``distance_from_spot`` : float -- max_pain - underlying_price.
            - ``distance_pct`` : float -- percentage distance.
            - ``historical_accuracy`` : float or None.
            - ``pain_profile`` : list[dict] -- pain by strike (strike, pain).
        """
        calls = chain.calls
        puts = chain.puts
        strikes = chain.strikes
        spot = chain.underlying_price

        if not strikes:
            return {
                "max_pain_strike": spot,
                "max_pain_value": 0.0,
                "pain_at_spot": 0.0,
                "pain_sensitivity": 0.0,
                "distance_from_spot": 0.0,
                "distance_pct": 0.0,
                "historical_accuracy": historical_accuracy,
                "pain_profile": [],
            }

        # Build OI lookup by strike
        call_oi_map: dict[float, int] = {}
        put_oi_map: dict[float, int] = {}
        for q in calls:
            call_oi_map[q.strike] = call_oi_map.get(q.strike, 0) + q.open_interest
        for q in puts:
            put_oi_map[q.strike] = put_oi_map.get(q.strike, 0) + q.open_interest

        # Compute pain at each strike
        pain_profile: list[dict] = []
        min_pain = float("inf")
        max_pain_strike = strikes[0]

        for test_price in strikes:
            total_pain = 0.0

            # Call pain: calls are ITM when test_price > strike
            for strike in strikes:
                oi = call_oi_map.get(strike, 0)
                if oi > 0 and test_price > strike:
                    total_pain += (test_price - strike) * oi * _CONTRACT_MULTIPLIER

            # Put pain: puts are ITM when test_price < strike
            for strike in strikes:
                oi = put_oi_map.get(strike, 0)
                if oi > 0 and test_price < strike:
                    total_pain += (strike - test_price) * oi * _CONTRACT_MULTIPLIER

            pain_profile.append({
                "strike": test_price,
                "pain": round(total_pain, 2),
            })

            if total_pain < min_pain:
                min_pain = total_pain
                max_pain_strike = test_price

        # Pain at current spot
        pain_at_spot = 0.0
        for strike in strikes:
            call_oi = call_oi_map.get(strike, 0)
            put_oi = put_oi_map.get(strike, 0)
            if call_oi > 0 and spot > strike:
                pain_at_spot += (spot - strike) * call_oi * _CONTRACT_MULTIPLIER
            if put_oi > 0 and spot < strike:
                pain_at_spot += (strike - spot) * put_oi * _CONTRACT_MULTIPLIER

        # Pain sensitivity: approximate derivative at max pain strike
        # Use the two neighbouring strikes for finite difference
        pain_values = {p["strike"]: p["pain"] for p in pain_profile}
        sensitivity = self._compute_pain_sensitivity(
            max_pain_strike, strikes, pain_values
        )

        distance = max_pain_strike - spot
        distance_pct = _safe_divide(distance, spot) * 100.0

        return {
            "max_pain_strike": max_pain_strike,
            "max_pain_value": round(min_pain, 2),
            "pain_at_spot": round(pain_at_spot, 2),
            "pain_sensitivity": round(sensitivity, 2),
            "distance_from_spot": round(distance, 2),
            "distance_pct": round(distance_pct, 4),
            "historical_accuracy": historical_accuracy,
            "pain_profile": pain_profile,
        }

    @staticmethod
    def _compute_pain_sensitivity(
        max_pain_strike: float,
        strikes: list[float],
        pain_values: dict[float, float],
    ) -> float:
        """Compute pain sensitivity (d_pain / d_price) near max pain.

        Uses central finite difference when possible, otherwise falls
        back to one-sided difference.
        """
        idx = strikes.index(max_pain_strike) if max_pain_strike in strikes else -1
        if idx < 0:
            return 0.0

        # Central difference
        if idx > 0 and idx < len(strikes) - 1:
            s_lo = strikes[idx - 1]
            s_hi = strikes[idx + 1]
            p_lo = pain_values.get(s_lo, 0.0)
            p_hi = pain_values.get(s_hi, 0.0)
            ds = s_hi - s_lo
            if ds > 0:
                return (p_hi - p_lo) / ds

        # One-sided fallback
        if idx < len(strikes) - 1:
            s_hi = strikes[idx + 1]
            p_mp = pain_values.get(max_pain_strike, 0.0)
            p_hi = pain_values.get(s_hi, 0.0)
            ds = s_hi - max_pain_strike
            if ds > 0:
                return (p_hi - p_mp) / ds

        return 0.0

    # -----------------------------------------------------------------
    # g) Dealer Exposure Summary
    # -----------------------------------------------------------------

    def compute_dealer_exposure_summary(
        self,
        chain: OptionsChain,
        spot: float,
    ) -> dict:
        """Comprehensive dealer exposure analysis.

        Assumes the standard dealer positioning model: dealers are short
        puts (customers buy protective puts) and long calls (customers
        sell covered calls). This is the classical Cboe assumption for
        SPX index options.

        Parameters
        ----------
        chain : OptionsChain
            Current options chain snapshot.
        spot : float
            Current SPX spot price.

        Returns
        -------
        dict
            - ``net_delta_exposure`` : float -- in ES-equivalent contracts.
            - ``net_gamma_exposure`` : float -- aggregate net GEX ($ per 1-pt move).
            - ``net_vanna_exposure`` : float -- aggregate vanna exposure.
            - ``net_charm_exposure`` : float -- aggregate charm exposure.
            - ``hedging_flow_direction`` : str -- ``"BUY"`` / ``"SELL"`` / ``"FLAT"``.
            - ``hedging_flow_magnitude_es`` : float -- estimated ES contracts
              dealer must trade to re-hedge for a 1-point spot move.
            - ``gamma_regime`` : str -- ``"POSITIVE"`` / ``"NEGATIVE"`` / ``"FLAT"``.
            - ``exposure_by_strike`` : list[dict] -- per-strike breakdown.
        """
        exposure_by_strike: list[dict] = []
        total_delta = 0.0
        total_gamma = 0.0
        total_vanna = 0.0
        total_charm = 0.0

        for strike in chain.strikes:
            quotes = chain.get_by_strike(strike)
            strike_delta = 0.0
            strike_gamma = 0.0
            strike_vanna = 0.0
            strike_charm = 0.0

            for q in quotes:
                oi = q.open_interest
                if oi == 0:
                    continue

                # Dealer position assumption:
                #   Calls: dealers are long (customers sold) -> dealer delta = +delta * OI
                #   Puts:  dealers are short (customers bought) -> dealer delta = +delta * OI
                #          (put delta is negative, so short put = positive delta exposure)
                if q.option_type == OptionSide.CALL:
                    # Customers net sell calls -> dealer long calls
                    dealer_sign = 1.0
                else:
                    # Customers net buy puts -> dealer short puts
                    # Short put delta = -1 * put_delta (put_delta < 0, so positive)
                    dealer_sign = -1.0

                notional_oi = float(oi) * _CONTRACT_MULTIPLIER

                strike_delta += dealer_sign * q.delta * notional_oi
                strike_gamma += dealer_sign * q.gamma * notional_oi
                strike_vanna += dealer_sign * q.vanna * notional_oi
                strike_charm += dealer_sign * q.charm * notional_oi

            total_delta += strike_delta
            total_gamma += strike_gamma
            total_vanna += strike_vanna
            total_charm += strike_charm

            exposure_by_strike.append({
                "strike": strike,
                "dealer_delta": round(strike_delta, 2),
                "dealer_gamma": round(strike_gamma, 2),
                "dealer_vanna": round(strike_vanna, 4),
                "dealer_charm": round(strike_charm, 4),
            })

        # Convert delta to ES-equivalent contracts
        # 1 ES contract = $50 per point, so delta in $ / ES multiplier
        delta_es = _safe_divide(total_delta, _ES_MULTIPLIER)

        # Hedging flow: with positive gamma, a spot increase means dealer
        # becomes more long delta, so they SELL to re-hedge (dampening).
        # With negative gamma, they must BUY into rallies (amplifying).
        hedging_magnitude = abs(total_gamma) / _ES_MULTIPLIER  # ES contracts per 1-pt move
        if total_gamma > _EPSILON:
            hedging_direction = "SELL"  # Positive gamma: sell into rallies
            gamma_regime = "POSITIVE"
        elif total_gamma < -_EPSILON:
            hedging_direction = "BUY"  # Negative gamma: buy into rallies
            gamma_regime = "NEGATIVE"
        else:
            hedging_direction = "FLAT"
            gamma_regime = "FLAT"

        return {
            "net_delta_exposure": round(delta_es, 2),
            "net_gamma_exposure": round(total_gamma, 2),
            "net_vanna_exposure": round(total_vanna, 4),
            "net_charm_exposure": round(total_charm, 4),
            "hedging_flow_direction": hedging_direction,
            "hedging_flow_magnitude_es": round(hedging_magnitude, 2),
            "gamma_regime": gamma_regime,
            "exposure_by_strike": exposure_by_strike,
        }

    # -----------------------------------------------------------------
    # h) Open Interest Profile
    # -----------------------------------------------------------------

    def compute_open_interest_profile(self, chain: OptionsChain) -> dict:
        """OI profile analysis.

        Parameters
        ----------
        chain : OptionsChain
            Current options chain snapshot.

        Returns
        -------
        dict
            - ``call_oi_by_strike`` : dict[float, int]
            - ``put_oi_by_strike`` : dict[float, int]
            - ``total_oi_by_strike`` : dict[float, int]
            - ``total_call_oi`` : int
            - ``total_put_oi`` : int
            - ``max_call_oi_strike`` : float -- strike with highest call OI.
            - ``max_put_oi_strike`` : float -- strike with highest put OI.
            - ``max_total_oi_strike`` : float -- strike with highest combined OI.
            - ``oi_concentration_pct`` : float -- % of total OI in top 5 strikes.
            - ``oi_clusters`` : list[dict] -- strikes with significant OI
              concentration that may act as magnets/barriers.
        """
        call_oi_map: dict[float, int] = defaultdict(int)
        put_oi_map: dict[float, int] = defaultdict(int)

        for q in chain.calls:
            call_oi_map[q.strike] += q.open_interest
        for q in chain.puts:
            put_oi_map[q.strike] += q.open_interest

        total_oi_map: dict[float, int] = {}
        all_strikes = chain.strikes
        for strike in all_strikes:
            total_oi_map[strike] = call_oi_map.get(strike, 0) + put_oi_map.get(strike, 0)

        total_call_oi = sum(call_oi_map.values())
        total_put_oi = sum(put_oi_map.values())
        total_oi = total_call_oi + total_put_oi

        # Strikes with highest OI
        max_call_strike = max(call_oi_map, key=call_oi_map.get, default=0.0) if call_oi_map else 0.0
        max_put_strike = max(put_oi_map, key=put_oi_map.get, default=0.0) if put_oi_map else 0.0
        max_total_strike = max(total_oi_map, key=total_oi_map.get, default=0.0) if total_oi_map else 0.0

        # OI concentration: top 5 strikes as % of total
        sorted_strikes = sorted(total_oi_map.items(), key=lambda x: x[1], reverse=True)
        top5_oi = sum(oi for _, oi in sorted_strikes[:5])
        concentration_pct = _safe_divide(float(top5_oi), float(total_oi)) * 100.0

        # Identify OI clusters (strikes with > 5% of total OI)
        oi_clusters: list[dict] = []
        for strike, oi in sorted_strikes:
            if total_oi > 0 and (oi / float(total_oi)) >= 0.03:
                call_at = call_oi_map.get(strike, 0)
                put_at = put_oi_map.get(strike, 0)
                pct = (oi / float(total_oi)) * 100.0
                cluster_type = "MAGNET" if call_at > put_at else "BARRIER"
                oi_clusters.append({
                    "strike": strike,
                    "total_oi": oi,
                    "call_oi": call_at,
                    "put_oi": put_at,
                    "pct_of_total": round(pct, 2),
                    "type": cluster_type,
                    "description": (
                        f"Strike {strike}: {oi:,} OI ({pct:.1f}% of total) "
                        f"-- {'call' if call_at > put_at else 'put'}-dominant "
                        f"({cluster_type.lower()})"
                    ),
                })

        return {
            "call_oi_by_strike": dict(call_oi_map),
            "put_oi_by_strike": dict(put_oi_map),
            "total_oi_by_strike": total_oi_map,
            "total_call_oi": total_call_oi,
            "total_put_oi": total_put_oi,
            "max_call_oi_strike": max_call_strike,
            "max_put_oi_strike": max_put_strike,
            "max_total_oi_strike": max_total_strike,
            "oi_concentration_pct": round(concentration_pct, 2),
            "oi_clusters": oi_clusters,
        }

    # -----------------------------------------------------------------
    # i) Volume Profile
    # -----------------------------------------------------------------

    def compute_volume_profile(self, chain: OptionsChain) -> dict:
        """Intraday volume profile analysis.

        Parameters
        ----------
        chain : OptionsChain
            Current options chain snapshot.

        Returns
        -------
        dict
            - ``call_volume_by_strike`` : dict[float, int]
            - ``put_volume_by_strike`` : dict[float, int]
            - ``total_volume_by_strike`` : dict[float, int]
            - ``total_call_volume`` : int
            - ``total_put_volume`` : int
            - ``total_volume`` : int
            - ``volume_weighted_avg_strike`` : float -- VWAS.
            - ``heavy_volume_strikes`` : list[float] -- strikes with > 5% of
              total volume.
            - ``light_volume_strikes`` : list[float] -- strikes with < 0.5% of
              total volume (among strikes that traded).
            - ``volume_concentration_top5_pct`` : float -- % of total volume
              in top 5 strikes.
        """
        call_vol_map: dict[float, int] = defaultdict(int)
        put_vol_map: dict[float, int] = defaultdict(int)

        for q in chain.calls:
            call_vol_map[q.strike] += q.volume
        for q in chain.puts:
            put_vol_map[q.strike] += q.volume

        total_vol_map: dict[float, int] = {}
        for strike in chain.strikes:
            total_vol_map[strike] = call_vol_map.get(strike, 0) + put_vol_map.get(strike, 0)

        total_call_vol = sum(call_vol_map.values())
        total_put_vol = sum(put_vol_map.values())
        total_vol = total_call_vol + total_put_vol

        # Volume-weighted average strike
        if total_vol > 0:
            vwas = sum(
                strike * vol for strike, vol in total_vol_map.items()
            ) / float(total_vol)
        else:
            vwas = chain.underlying_price

        # Heavy and light volume strikes
        heavy: list[float] = []
        light: list[float] = []
        for strike, vol in total_vol_map.items():
            if total_vol > 0:
                pct = vol / float(total_vol)
                if pct >= 0.05:
                    heavy.append(strike)
                elif 0 < vol and pct < 0.005:
                    light.append(strike)

        # Top-5 concentration
        sorted_vols = sorted(total_vol_map.items(), key=lambda x: x[1], reverse=True)
        top5_vol = sum(vol for _, vol in sorted_vols[:5])
        concentration = _safe_divide(float(top5_vol), float(total_vol)) * 100.0

        return {
            "call_volume_by_strike": dict(call_vol_map),
            "put_volume_by_strike": dict(put_vol_map),
            "total_volume_by_strike": total_vol_map,
            "total_call_volume": total_call_vol,
            "total_put_volume": total_put_vol,
            "total_volume": total_vol,
            "volume_weighted_avg_strike": round(vwas, 2),
            "heavy_volume_strikes": sorted(heavy),
            "light_volume_strikes": sorted(light),
            "volume_concentration_top5_pct": round(concentration, 2),
        }

    # -----------------------------------------------------------------
    # j) Hedging Clusters
    # -----------------------------------------------------------------

    def identify_hedging_clusters(
        self,
        chain: OptionsChain,
        spot: float,
        top_n: int = 10,
    ) -> list[dict]:
        """Identify strike clusters where significant hedging activity occurs.

        These are strikes where dealer gamma is concentrated and hedging
        flows will be most intense if price approaches.

        Parameters
        ----------
        chain : OptionsChain
            Current options chain snapshot.
        spot : float
            Current SPX spot price.
        top_n : int
            Maximum number of clusters to return.

        Returns
        -------
        list[dict]
            Each cluster dict contains:
            - ``strike`` : float
            - ``net_gamma`` : float -- net dealer gamma at this strike ($ per 1-pt).
            - ``call_gamma_component`` : float
            - ``put_gamma_component`` : float
            - ``distance_from_spot`` : float -- signed distance in points.
            - ``distance_pct`` : float -- percentage distance.
            - ``hedging_intensity`` : str -- ``"EXTREME"`` / ``"HIGH"`` / ``"MODERATE"``.
            - ``expected_effect`` : str -- description of expected price effect.
        """
        gamma_by_strike: list[dict] = []

        for strike in chain.strikes:
            quotes = chain.get_by_strike(strike)
            call_gamma_sum = 0.0
            put_gamma_sum = 0.0

            for q in quotes:
                oi = q.open_interest
                if oi == 0:
                    continue
                notional = float(oi) * _CONTRACT_MULTIPLIER

                if q.option_type == OptionSide.CALL:
                    # Dealers long calls -> long gamma
                    call_gamma_sum += q.gamma * notional
                else:
                    # Dealers short puts -> short gamma (puts have positive gamma,
                    # but dealer is short, so net contribution is negative)
                    put_gamma_sum -= q.gamma * notional

            net_gamma = call_gamma_sum + put_gamma_sum
            distance = strike - spot
            distance_pct = _safe_divide(distance, spot) * 100.0

            gamma_by_strike.append({
                "strike": strike,
                "net_gamma": net_gamma,
                "call_gamma_component": call_gamma_sum,
                "put_gamma_component": put_gamma_sum,
                "abs_gamma": abs(net_gamma),
                "distance_from_spot": distance,
                "distance_pct": distance_pct,
            })

        # Sort by absolute gamma descending and take top N
        gamma_by_strike.sort(key=lambda x: x["abs_gamma"], reverse=True)
        top_clusters = gamma_by_strike[:top_n]

        # Compute intensity thresholds from the distribution
        all_abs = [g["abs_gamma"] for g in gamma_by_strike if g["abs_gamma"] > 0]
        if all_abs:
            p90 = float(np.percentile(all_abs, 90))
            p70 = float(np.percentile(all_abs, 70))
        else:
            p90, p70 = float("inf"), float("inf")

        results: list[dict] = []
        for cluster in top_clusters:
            if cluster["abs_gamma"] <= 0:
                continue

            # Intensity classification
            if cluster["abs_gamma"] >= p90:
                intensity = "EXTREME"
            elif cluster["abs_gamma"] >= p70:
                intensity = "HIGH"
            else:
                intensity = "MODERATE"

            # Expected effect when price approaches this strike
            if cluster["net_gamma"] > 0:
                effect = (
                    f"Positive gamma at {cluster['strike']}: dealer hedging will "
                    f"DAMPEN moves, acting as resistance/support (mean-reversion magnet)."
                )
            else:
                effect = (
                    f"Negative gamma at {cluster['strike']}: dealer hedging will "
                    f"AMPLIFY moves, acting as breakout accelerator."
                )

            results.append({
                "strike": cluster["strike"],
                "net_gamma": round(cluster["net_gamma"], 2),
                "call_gamma_component": round(cluster["call_gamma_component"], 2),
                "put_gamma_component": round(cluster["put_gamma_component"], 2),
                "distance_from_spot": round(cluster["distance_from_spot"], 2),
                "distance_pct": round(cluster["distance_pct"], 4),
                "hedging_intensity": intensity,
                "expected_effect": effect,
            })

        logger.info(
            "Identified %d hedging clusters from %d strikes.",
            len(results),
            len(chain.strikes),
        )
        return results


# =========================================================================
# 2. FlowClassifier
# =========================================================================


class FlowClassifier:
    """Classifies individual options trades by intent.

    Provides granular trade-level classification for aggressor detection,
    institutional vs retail heuristics, and sweep/block identification.
    Designed to consume real-time trade prints from the options tape.

    Usage::

        classifier = FlowClassifier()
        classified = classifier.classify_trade(trade, chain)
        sweeps = classifier.detect_sweep(trades)
        is_block = classifier.detect_block_trade(trade)
    """

    # Size heuristics
    _INSTITUTIONAL_SIZE_THRESHOLD: int = 50  # >= 50 contracts likely institutional
    _RETAIL_SIZE_THRESHOLD: int = 10  # <= 10 contracts likely retail
    _SPREAD_PROXIMITY_PCT: float = 0.10  # Within 10% of OI match = spread candidate

    # -----------------------------------------------------------------
    # a) Classify Single Trade
    # -----------------------------------------------------------------

    def classify_trade(
        self,
        trade: dict,
        chain_snapshot: OptionsChain,
    ) -> dict:
        """Classify a single options trade.

        Parameters
        ----------
        trade : dict
            Trade record with fields: ``strike``, ``option_type`` (str),
            ``size`` (int), ``price`` (float), ``side`` (``"BUY"`` /
            ``"SELL"``), ``timestamp`` (datetime or str), and optionally
            ``exchange`` (str).
        chain_snapshot : OptionsChain
            Current chain state for context.

        Returns
        -------
        dict
            - ``opening_closing`` : str -- ``"OPENING"`` / ``"CLOSING"`` / ``"UNKNOWN"``.
            - ``aggressor_side`` : str -- ``"BUY"`` / ``"SELL"`` / ``"UNKNOWN"``.
            - ``trade_intent`` : str -- ``"HEDGING"`` / ``"SPECULATIVE"`` / ``"SPREAD"``.
            - ``participant_type`` : str -- ``"INSTITUTIONAL"`` / ``"RETAIL"`` / ``"UNKNOWN"``.
            - ``is_block`` : bool
            - ``is_sweep`` : bool (always False for single trade; use ``detect_sweep``).
            - ``premium_dollars`` : float -- notional premium of the trade.
            - ``directional_impact`` : str -- ``"BULLISH"`` / ``"BEARISH"`` / ``"NEUTRAL"``.
        """
        strike = trade.get("strike", 0.0)
        option_type_str = trade.get("option_type", "CALL")
        size = trade.get("size", 0)
        price = trade.get("price", 0.0)
        side = trade.get("side", "UNKNOWN")

        premium_dollars = float(size) * price * _CONTRACT_MULTIPLIER

        # --- Opening vs Closing ---
        opening_closing = self._classify_opening_closing(
            strike, option_type_str, size, chain_snapshot
        )

        # --- Aggressor side ---
        aggressor = self._classify_aggressor(trade, chain_snapshot)

        # --- Trade intent ---
        intent = self._classify_intent(trade, chain_snapshot)

        # --- Participant type ---
        participant = self._classify_participant(size)

        # --- Block trade ---
        is_block = self.detect_block_trade(trade)

        # --- Directional impact ---
        directional = self._compute_directional_impact(
            option_type_str, side, opening_closing
        )

        return {
            "opening_closing": opening_closing,
            "aggressor_side": aggressor,
            "trade_intent": intent,
            "participant_type": participant,
            "is_block": is_block,
            "is_sweep": False,  # Single trade cannot be a sweep
            "premium_dollars": round(premium_dollars, 2),
            "directional_impact": directional,
        }

    def _classify_opening_closing(
        self,
        strike: float,
        option_type_str: str,
        size: int,
        chain: OptionsChain,
    ) -> str:
        """Heuristic: if volume at this strike exceeds OI, likely opening."""
        matching = [
            q for q in chain.quotes
            if q.strike == strike and q.option_type.value == option_type_str
        ]
        if not matching:
            return "UNKNOWN"

        q = matching[0]
        # If adding this trade would push volume past OI, likely opening
        if q.volume + size > q.open_interest:
            return "OPENING"
        elif q.open_interest > 0 and q.volume > q.open_interest * 0.5:
            return "CLOSING"
        return "UNKNOWN"

    def _classify_aggressor(
        self,
        trade: dict,
        chain: OptionsChain,
    ) -> str:
        """Determine if trade was buyer or seller initiated.

        Uses price relative to mid: above mid = buyer-initiated,
        below mid = seller-initiated.
        """
        strike = trade.get("strike", 0.0)
        option_type_str = trade.get("option_type", "CALL")
        price = trade.get("price", 0.0)

        matching = [
            q for q in chain.quotes
            if q.strike == strike and q.option_type.value == option_type_str
        ]
        if not matching:
            return trade.get("side", "UNKNOWN")

        q = matching[0]
        mid = q.mid
        if mid <= 0:
            return trade.get("side", "UNKNOWN")

        # Above mid = buyer aggressor, below = seller aggressor
        if price >= mid * 1.001:  # Small tolerance for rounding
            return "BUY"
        elif price <= mid * 0.999:
            return "SELL"
        return trade.get("side", "UNKNOWN")

    def _classify_intent(
        self,
        trade: dict,
        chain: OptionsChain,
    ) -> str:
        """Classify trade intent as hedging, speculative, or spread.

        Heuristics:
        - Large OTM puts on high OI = likely hedging
        - Moderate size, ATM strikes = likely speculative
        - Paired volume at adjacent strikes = likely spread
        """
        strike = trade.get("strike", 0.0)
        option_type_str = trade.get("option_type", "CALL")
        size = trade.get("size", 0)
        spot = chain.underlying_price

        # Distance from ATM
        distance_pct = abs(strike - spot) / spot if spot > 0 else 0.0

        # Check for potential spread: look for similar volume at nearby strikes
        for q in chain.quotes:
            if (
                q.option_type.value == option_type_str
                and q.strike != strike
                and abs(q.strike - strike) <= 10  # Within $10 (two strike widths)
                and q.volume > 0
            ):
                # Similar volume at adjacent strike suggests spread
                volume_ratio = min(size, q.volume) / max(size, q.volume) if max(size, q.volume) > 0 else 0
                if volume_ratio > 0.5:
                    return "SPREAD"

        # OTM puts with large size = hedging
        if (
            option_type_str == "PUT"
            and strike < spot
            and distance_pct > 0.02
            and size >= self._INSTITUTIONAL_SIZE_THRESHOLD
        ):
            return "HEDGING"

        return "SPECULATIVE"

    def _classify_participant(self, size: int) -> str:
        """Size-based heuristic for institutional vs retail."""
        if size >= self._INSTITUTIONAL_SIZE_THRESHOLD:
            return "INSTITUTIONAL"
        elif size <= self._RETAIL_SIZE_THRESHOLD:
            return "RETAIL"
        return "UNKNOWN"

    @staticmethod
    def _compute_directional_impact(
        option_type_str: str,
        side: str,
        opening_closing: str,
    ) -> str:
        """Determine directional impact of the trade.

        Opening buy call / closing sell put = BULLISH
        Opening buy put / closing sell call = BEARISH
        """
        is_call = option_type_str == "CALL"
        is_buy = side == "BUY"
        is_opening = opening_closing == "OPENING"

        if is_call:
            if (is_buy and is_opening) or (not is_buy and not is_opening):
                return "BULLISH"
            elif (not is_buy and is_opening) or (is_buy and not is_opening):
                return "BEARISH"
        else:
            # PUT
            if (is_buy and is_opening) or (not is_buy and not is_opening):
                return "BEARISH"
            elif (not is_buy and is_opening) or (is_buy and not is_opening):
                return "BULLISH"

        return "NEUTRAL"

    # -----------------------------------------------------------------
    # b) Aggregate Flow
    # -----------------------------------------------------------------

    def aggregate_flow(
        self,
        trades: list[dict],
        window_minutes: int = 5,
    ) -> dict:
        """Aggregate classified trades over a rolling window.

        Parameters
        ----------
        trades : list[dict]
            List of trade dicts, each with at minimum: ``strike``,
            ``option_type``, ``size``, ``price``, ``side``, ``timestamp``.
        window_minutes : int
            Lookback window in minutes. Trades older than this are excluded.

        Returns
        -------
        dict
            - ``net_bullish_premium`` : float -- bullish premium in $.
            - ``net_bearish_premium`` : float -- bearish premium in $.
            - ``net_flow`` : float -- bullish - bearish (positive = bullish).
            - ``net_signal`` : float -- normalized signal [-1, +1].
            - ``call_flow_net`` : float -- net call premium (buy - sell).
            - ``put_flow_net`` : float -- net put premium (buy - sell).
            - ``block_direction`` : str -- ``"BULLISH"`` / ``"BEARISH"`` / ``"NEUTRAL"``.
            - ``sweep_direction`` : str -- ``"BULLISH"`` / ``"BEARISH"`` / ``"NEUTRAL"``.
            - ``trade_count`` : int -- trades within window.
        """
        if not trades:
            return {
                "net_bullish_premium": 0.0,
                "net_bearish_premium": 0.0,
                "net_flow": 0.0,
                "net_signal": 0.0,
                "call_flow_net": 0.0,
                "put_flow_net": 0.0,
                "block_direction": "NEUTRAL",
                "sweep_direction": "NEUTRAL",
                "trade_count": 0,
            }

        # Filter by window
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=window_minutes)
        windowed: list[dict] = []
        for t in trades:
            ts = t.get("timestamp")
            if ts is None:
                windowed.append(t)
                continue
            if isinstance(ts, str):
                try:
                    ts = datetime.fromisoformat(ts)
                except (ValueError, TypeError):
                    windowed.append(t)
                    continue
            if ts >= cutoff:
                windowed.append(t)

        bullish_premium = 0.0
        bearish_premium = 0.0
        call_buy = 0.0
        call_sell = 0.0
        put_buy = 0.0
        put_sell = 0.0
        block_bullish = 0.0
        block_bearish = 0.0

        for t in windowed:
            size = t.get("size", 0)
            price = t.get("price", 0.0)
            side = t.get("side", "UNKNOWN")
            option_type_str = t.get("option_type", "CALL")
            premium = float(size) * price * _CONTRACT_MULTIPLIER
            is_call = option_type_str == "CALL"
            is_buy = side == "BUY"

            # Directional classification
            if is_call and is_buy:
                bullish_premium += premium
                call_buy += premium
            elif is_call and not is_buy:
                bearish_premium += premium
                call_sell += premium
            elif not is_call and is_buy:
                bearish_premium += premium
                put_buy += premium
            elif not is_call and not is_buy:
                bullish_premium += premium
                put_sell += premium

            # Block trade tracking
            if size >= _BLOCK_TRADE_THRESHOLD:
                if (is_call and is_buy) or (not is_call and not is_buy):
                    block_bullish += premium
                else:
                    block_bearish += premium

        net_flow = bullish_premium - bearish_premium
        total = bullish_premium + bearish_premium
        net_signal = _safe_divide(net_flow, total)  # [-1, +1]

        call_flow_net = call_buy - call_sell
        put_flow_net = put_buy - put_sell

        # Block direction
        if block_bullish > block_bearish * 1.5:
            block_dir = "BULLISH"
        elif block_bearish > block_bullish * 1.5:
            block_dir = "BEARISH"
        else:
            block_dir = "NEUTRAL"

        # Sweep detection
        sweeps = self.detect_sweep(windowed)
        sweep_bullish = sum(
            s.get("premium", 0.0) for s in sweeps if s.get("direction") == "BULLISH"
        )
        sweep_bearish = sum(
            s.get("premium", 0.0) for s in sweeps if s.get("direction") == "BEARISH"
        )
        if sweep_bullish > sweep_bearish * 1.5:
            sweep_dir = "BULLISH"
        elif sweep_bearish > sweep_bullish * 1.5:
            sweep_dir = "BEARISH"
        else:
            sweep_dir = "NEUTRAL"

        return {
            "net_bullish_premium": round(bullish_premium, 2),
            "net_bearish_premium": round(bearish_premium, 2),
            "net_flow": round(net_flow, 2),
            "net_signal": round(net_signal, 4),
            "call_flow_net": round(call_flow_net, 2),
            "put_flow_net": round(put_flow_net, 2),
            "block_direction": block_dir,
            "sweep_direction": sweep_dir,
            "trade_count": len(windowed),
        }

    # -----------------------------------------------------------------
    # c) Sweep Detection
    # -----------------------------------------------------------------

    def detect_sweep(
        self,
        trades: list[dict],
        time_window_seconds: int = _SWEEP_TIME_WINDOW_SECONDS,
    ) -> list[dict]:
        """Detect multi-exchange sweep orders (indicate urgency).

        A sweep is defined as multiple trades on the same option contract
        (same strike and type), in the same direction, occurring within
        *time_window_seconds* across different exchanges.

        Parameters
        ----------
        trades : list[dict]
            Trades with fields: ``strike``, ``option_type``, ``size``,
            ``price``, ``side``, ``timestamp``, ``exchange``.
        time_window_seconds : int
            Maximum time gap between legs of a sweep.

        Returns
        -------
        list[dict]
            Each sweep dict contains:
            - ``strike`` : float
            - ``option_type`` : str
            - ``side`` : str
            - ``total_size`` : int
            - ``exchanges`` : list[str]
            - ``trade_count`` : int
            - ``premium`` : float
            - ``direction`` : str -- ``"BULLISH"`` / ``"BEARISH"``.
            - ``time_span_seconds`` : float
        """
        if not trades:
            return []

        # Group trades by (strike, option_type, side)
        groups: dict[Tuple[float, str, str], list[dict]] = defaultdict(list)
        for t in trades:
            key = (
                t.get("strike", 0.0),
                t.get("option_type", "CALL"),
                t.get("side", "UNKNOWN"),
            )
            groups[key].append(t)

        sweeps: list[dict] = []

        for (strike, otype, side), group_trades in groups.items():
            if len(group_trades) < 2:
                continue

            # Sort by timestamp
            def _parse_ts(t: dict) -> datetime:
                ts = t.get("timestamp")
                if isinstance(ts, datetime):
                    return ts
                if isinstance(ts, str):
                    try:
                        return datetime.fromisoformat(ts)
                    except (ValueError, TypeError):
                        pass
                return datetime.now(timezone.utc)

            sorted_trades = sorted(group_trades, key=_parse_ts)

            # Sliding window to find sweep clusters
            i = 0
            while i < len(sorted_trades):
                cluster = [sorted_trades[i]]
                j = i + 1
                while j < len(sorted_trades):
                    ts_prev = _parse_ts(cluster[-1])
                    ts_curr = _parse_ts(sorted_trades[j])
                    gap = abs((ts_curr - ts_prev).total_seconds())
                    if gap <= time_window_seconds:
                        cluster.append(sorted_trades[j])
                        j += 1
                    else:
                        break

                # Need >= 2 trades from different exchanges
                exchanges = list({
                    t.get("exchange", "UNKNOWN") for t in cluster
                })
                if len(cluster) >= 2 and len(exchanges) >= 2:
                    total_size = sum(t.get("size", 0) for t in cluster)
                    total_premium = sum(
                        t.get("size", 0) * t.get("price", 0.0) * _CONTRACT_MULTIPLIER
                        for t in cluster
                    )
                    time_span = abs(
                        (_parse_ts(cluster[-1]) - _parse_ts(cluster[0])).total_seconds()
                    )

                    # Direction
                    is_call = otype == "CALL"
                    is_buy = side == "BUY"
                    if (is_call and is_buy) or (not is_call and not is_buy):
                        direction = "BULLISH"
                    else:
                        direction = "BEARISH"

                    sweeps.append({
                        "strike": strike,
                        "option_type": otype,
                        "side": side,
                        "total_size": total_size,
                        "exchanges": exchanges,
                        "trade_count": len(cluster),
                        "premium": round(total_premium, 2),
                        "direction": direction,
                        "time_span_seconds": round(time_span, 3),
                    })

                i = j

        # Sort by premium descending (most significant sweeps first)
        sweeps.sort(key=lambda s: s["premium"], reverse=True)

        logger.info("Sweep detection: %d sweeps identified.", len(sweeps))
        return sweeps

    # -----------------------------------------------------------------
    # d) Block Trade Detection
    # -----------------------------------------------------------------

    def detect_block_trade(
        self,
        trade: dict,
        threshold: int = _BLOCK_TRADE_THRESHOLD,
    ) -> bool:
        """Identify block trades (>= threshold contracts).

        Parameters
        ----------
        trade : dict
            Single trade record with at least a ``size`` field.
        threshold : int
            Minimum number of contracts to qualify as a block.

        Returns
        -------
        bool
            True if trade size >= threshold.
        """
        size = trade.get("size", 0)
        return size >= threshold


# =========================================================================
# Module-level convenience (for direct import from package)
# =========================================================================

__all__: list[str] = [
    "ChainAnalyzer",
    "FlowClassifier",
]
