"""
Precision Alpha Scanner — Unified Day-Trading & Scalping Engine for Optionable Stocks

Synthesizes 8 orthogonal signal dimensions into a single composite score per stock:

    1. Tape Pressure      — Aggressor flow, VPIN toxicity, block clustering
    2. Options Catalyst    — Unusual vol/OI, sweeps, premium-weighted flow
    3. Gamma Leverage      — Per-stock dealer GEX, gamma walls, pin risk
    4. Volatility Edge     — IV rank, skew z-score, IV vs RV spread, term structure
    5. Momentum Confluence — Multi-TF trend alignment, RSI divergence, MACD accel
    6. Volume Profile      — VWAP σ-bands, relative volume, POC deviation
    7. Market Regime       — Sector RS, SPY correlation, VIX regime, internals
    8. Structural Setup    — Key levels, FVG, order blocks, liquidity sweeps

Each dimension outputs 0-100.  Weights adapt to the current volatility regime.
Final composite ≥ 70 → actionable trade with optimal option contract selection.
"""

from __future__ import annotations

import logging
import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional, Any

from .base import BaseScanner, MarketData, HistoricalData, ScanContext
from .models import (
    ScanMode,
    ScanResult,
    ScannerConfig,
    SignalDirection,
    TimeFrame,
    MarketRegime,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SIGNAL_THRESHOLD = 70
HIGH_CONVICTION = 85

# Regime-adaptive weight presets  (must sum to 1.0)
#                       tape  opts  gamma  vol  mom   vpro  regime struct
WEIGHTS_LOW_VOL     = [0.10, 0.15, 0.10, 0.10, 0.20, 0.15, 0.10, 0.10]
WEIGHTS_NORMAL      = [0.12, 0.15, 0.12, 0.10, 0.18, 0.12, 0.11, 0.10]
WEIGHTS_HIGH_VOL    = [0.15, 0.18, 0.15, 0.12, 0.10, 0.08, 0.12, 0.10]
WEIGHTS_TRENDING    = [0.08, 0.12, 0.08, 0.08, 0.25, 0.15, 0.12, 0.12]
WEIGHTS_MEAN_REV    = [0.12, 0.12, 0.15, 0.15, 0.08, 0.18, 0.10, 0.10]

DIM_NAMES = [
    "tape_pressure",
    "options_catalyst",
    "gamma_leverage",
    "volatility_edge",
    "momentum_confluence",
    "volume_profile",
    "market_regime",
    "structural_setup",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _z_score(value: float, mean: float, std: float) -> float:
    if std < 1e-9:
        return 0.0
    return (value - mean) / std


def _ema(values: list[float], span: int) -> list[float]:
    if not values:
        return []
    alpha = 2.0 / (span + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(alpha * v + (1 - alpha) * out[-1])
    return out


def _rsi(closes: list[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    recent = deltas[-period:]
    gains = [d for d in recent if d > 0]
    losses = [-d for d in recent if d < 0]
    avg_gain = sum(gains) / period if gains else 0.0
    avg_loss = sum(losses) / period if losses else 1e-9
    rs = avg_gain / avg_loss if avg_loss > 1e-9 else 100.0
    return 100.0 - (100.0 / (1.0 + rs))


def _macd(closes: list[float]) -> tuple[float, float, float]:
    """Returns (macd_line, signal_line, histogram)."""
    if len(closes) < 26:
        return 0.0, 0.0, 0.0
    fast = _ema(closes, 12)
    slow = _ema(closes, 26)
    macd_line = [f - s for f, s in zip(fast, slow)]
    signal = _ema(macd_line, 9)
    return macd_line[-1], signal[-1], macd_line[-1] - signal[-1]


def _adx(highs: list[float], lows: list[float], closes: list[float],
         period: int = 14) -> tuple[float, float, float]:
    """Returns (adx, plus_di, minus_di)."""
    n = len(closes)
    if n < period + 1:
        return 20.0, 50.0, 50.0
    tr_list, plus_dm_list, minus_dm_list = [], [], []
    for i in range(1, n):
        tr = max(highs[i] - lows[i],
                 abs(highs[i] - closes[i - 1]),
                 abs(lows[i] - closes[i - 1]))
        up_move = highs[i] - highs[i - 1]
        down_move = lows[i - 1] - lows[i]
        plus_dm_list.append(up_move if up_move > down_move and up_move > 0 else 0.0)
        minus_dm_list.append(down_move if down_move > up_move and down_move > 0 else 0.0)
        tr_list.append(tr)

    atr = sum(tr_list[:period]) / period
    plus_dm = sum(plus_dm_list[:period]) / period
    minus_dm = sum(minus_dm_list[:period]) / period

    for i in range(period, len(tr_list)):
        atr = (atr * (period - 1) + tr_list[i]) / period
        plus_dm = (plus_dm * (period - 1) + plus_dm_list[i]) / period
        minus_dm = (minus_dm * (period - 1) + minus_dm_list[i]) / period

    plus_di = 100.0 * plus_dm / atr if atr > 0 else 0.0
    minus_di = 100.0 * minus_dm / atr if atr > 0 else 0.0
    dx = 100.0 * abs(plus_di - minus_di) / (plus_di + minus_di) if (plus_di + minus_di) > 0 else 0.0
    return dx, plus_di, minus_di


def _atr(highs: list[float], lows: list[float], closes: list[float],
         period: int = 14) -> float:
    n = len(closes)
    if n < 2:
        return 0.0
    trs = []
    for i in range(1, n):
        trs.append(max(highs[i] - lows[i],
                       abs(highs[i] - closes[i - 1]),
                       abs(lows[i] - closes[i - 1])))
    if len(trs) < period:
        return sum(trs) / len(trs) if trs else 0.0
    return sum(trs[-period:]) / period


def _vwap(highs: list[float], lows: list[float], closes: list[float],
          volumes: list[int]) -> float:
    cum_tp_vol = 0.0
    cum_vol = 0
    for h, l, c, v in zip(highs, lows, closes, volumes):
        tp = (h + l + c) / 3.0
        cum_tp_vol += tp * v
        cum_vol += v
    return cum_tp_vol / cum_vol if cum_vol > 0 else closes[-1]


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class OptionRecommendation:
    """Optimal option contract for the trade."""
    option_type: str          # "CALL" or "PUT"
    strike: float
    expiry_days: int          # DTE
    delta: float
    estimated_premium: float
    breakeven: float
    max_risk: float
    target_pnl_pct: float     # expected % return on premium
    greeks: dict[str, float] = field(default_factory=dict)


@dataclass
class DimensionScore:
    """Score for a single signal dimension."""
    name: str
    score: float              # 0-100
    direction: float          # -1 (bearish) to +1 (bullish)
    components: dict[str, float] = field(default_factory=dict)


@dataclass
class PrecisionAlphaResult:
    """Full output of the Precision Alpha Scanner for one symbol."""
    symbol: str
    composite_score: float
    direction: SignalDirection
    confidence: float
    dimensions: list[DimensionScore]
    entry_price: float
    stop_loss: float
    targets: list[float]
    risk_reward: float
    option_rec: Optional[OptionRecommendation]
    regime: str
    weights_used: list[float]
    timestamp: datetime


# ---------------------------------------------------------------------------
# Dimension scorers
# ---------------------------------------------------------------------------

class _TapePressureScorer:
    """Dimension 1: Microstructure — aggressor flow, VPIN, block clustering."""

    @staticmethod
    def score(md: MarketData, hist: HistoricalData,
              ctx: ScanContext) -> DimensionScore:
        components: dict[str, float] = {}
        direction_sum = 0.0
        score_pts = 0.0

        # --- Aggressor flow (bid/ask imbalance) ---
        if md.bid_size and md.ask_size and (md.bid_size + md.ask_size) > 0:
            imbalance = (md.bid_size - md.ask_size) / (md.bid_size + md.ask_size)
            components["bid_ask_imbalance"] = round(imbalance, 3)
            score_pts += _clamp(abs(imbalance) * 80, 0, 30)
            direction_sum += imbalance
        else:
            components["bid_ask_imbalance"] = 0.0

        # --- Relative volume spike (proxy for informed flow) ---
        if md.relative_volume and md.relative_volume > 0:
            rv = md.relative_volume
            components["relative_volume"] = round(rv, 2)
            if rv >= 3.0:
                score_pts += 25
            elif rv >= 2.0:
                score_pts += 18
            elif rv >= 1.5:
                score_pts += 10
            else:
                score_pts += 3
        else:
            components["relative_volume"] = 1.0

        # --- VPIN proxy (volume-synchronised toxicity) ---
        bars = hist.bars if hist else []
        if len(bars) >= 20:
            buy_vol, sell_vol = 0.0, 0.0
            for b in bars[-20:]:
                mid = (b.high + b.low) / 2.0
                frac_buy = (b.close - b.low) / (b.high - b.low) if b.high > b.low else 0.5
                buy_vol += b.volume * frac_buy
                sell_vol += b.volume * (1 - frac_buy)
            total = buy_vol + sell_vol
            vpin = abs(buy_vol - sell_vol) / total if total > 0 else 0.0
            components["vpin"] = round(vpin, 4)
            score_pts += _clamp(vpin * 60, 0, 25)
            direction_sum += (buy_vol - sell_vol) / total if total > 0 else 0.0
        else:
            components["vpin"] = 0.0

        # --- Spread compression (tight spread = institutional interest) ---
        if md.spread is not None and md.close > 0:
            spread_pct = md.spread / md.close * 100
            components["spread_pct"] = round(spread_pct, 4)
            if spread_pct < 0.02:
                score_pts += 20
            elif spread_pct < 0.05:
                score_pts += 12
            elif spread_pct < 0.10:
                score_pts += 5
        else:
            components["spread_pct"] = 0.0

        final = _clamp(score_pts)
        d = max(-1.0, min(1.0, direction_sum))
        return DimensionScore("tape_pressure", final, d, components)


class _OptionsCatalystScorer:
    """Dimension 2: Unusual options activity — vol/OI, sweeps, flow imbalance."""

    @staticmethod
    def score(md: MarketData, hist: HistoricalData,
              ctx: ScanContext) -> DimensionScore:
        components: dict[str, float] = {}
        score_pts = 0.0
        direction_sum = 0.0

        opts = ctx.metadata.get("options_data", {}) if ctx else {}

        # --- Volume / OI ratio ---
        vol_oi = opts.get("volume_oi_ratio", 0.0)
        components["vol_oi_ratio"] = round(vol_oi, 2)
        if vol_oi >= 2.0:
            score_pts += 30
        elif vol_oi >= 1.0:
            score_pts += 22
        elif vol_oi >= 0.5:
            score_pts += 12

        # --- Sweep count (aggressive fills across exchanges) ---
        sweeps = opts.get("sweep_count", 0)
        components["sweep_count"] = sweeps
        score_pts += _clamp(sweeps * 5, 0, 20)

        # --- Premium-weighted put/call flow ---
        call_prem = opts.get("net_call_premium", 0.0)
        put_prem = opts.get("net_put_premium", 0.0)
        total_prem = abs(call_prem) + abs(put_prem)
        if total_prem > 0:
            flow_ratio = (call_prem - put_prem) / total_prem
            components["premium_flow_ratio"] = round(flow_ratio, 3)
            score_pts += _clamp(abs(flow_ratio) * 30, 0, 20)
            direction_sum += flow_ratio
        else:
            components["premium_flow_ratio"] = 0.0

        # --- IV rank (cheap options = high leverage opportunity) ---
        iv_rank = opts.get("iv_rank", 50.0)
        components["iv_rank"] = round(iv_rank, 1)
        if iv_rank < 20:
            score_pts += 15
        elif iv_rank < 35:
            score_pts += 10
        elif iv_rank > 80:
            score_pts += 8

        # --- Block trades (>100 contracts, single leg) ---
        blocks = opts.get("block_count", 0)
        components["block_count"] = blocks
        score_pts += _clamp(blocks * 5, 0, 15)
        block_dir = opts.get("block_net_direction", 0.0)
        direction_sum += block_dir * 0.3

        final = _clamp(score_pts)
        d = max(-1.0, min(1.0, direction_sum))
        return DimensionScore("options_catalyst", final, d, components)


class _GammaLeverageScorer:
    """Dimension 3: Per-stock dealer gamma exposure, walls, pin risk."""

    @staticmethod
    def score(md: MarketData, hist: HistoricalData,
              ctx: ScanContext) -> DimensionScore:
        components: dict[str, float] = {}
        score_pts = 0.0
        direction_sum = 0.0

        gex = ctx.metadata.get("gex_data", {}) if ctx else {}

        # --- Net dealer gamma sign (negative = amplification) ---
        net_gex = gex.get("net_dealer_gamma", 0.0)
        components["net_dealer_gamma"] = round(net_gex, 2)
        if net_gex < -0.5:
            score_pts += 25
        elif net_gex < 0:
            score_pts += 15
        elif net_gex > 0.5:
            score_pts += 8

        # --- Gamma wall proximity ---
        call_wall = gex.get("call_wall", 0.0)
        put_wall = gex.get("put_wall", 0.0)
        price = md.close
        if call_wall > 0 and price > 0:
            dist_call = abs(price - call_wall) / price
            components["call_wall_dist_pct"] = round(dist_call * 100, 2)
            if dist_call < 0.005:
                score_pts += 20
                direction_sum -= 0.3
            elif dist_call < 0.01:
                score_pts += 12
        if put_wall > 0 and price > 0:
            dist_put = abs(price - put_wall) / price
            components["put_wall_dist_pct"] = round(dist_put * 100, 2)
            if dist_put < 0.005:
                score_pts += 20
                direction_sum += 0.3
            elif dist_put < 0.01:
                score_pts += 12

        # --- Gamma flip level (zero-GEX crossing) ---
        gamma_flip = gex.get("gamma_flip_level", 0.0)
        if gamma_flip > 0 and price > 0:
            above_flip = price > gamma_flip
            dist_flip = abs(price - gamma_flip) / price
            components["gamma_flip_dist_pct"] = round(dist_flip * 100, 2)
            if dist_flip < 0.003:
                score_pts += 18
            direction_sum += 0.2 if above_flip else -0.2

        # --- Max pain magnet ---
        max_pain = gex.get("max_pain", 0.0)
        if max_pain > 0 and price > 0:
            pain_dist = (price - max_pain) / price
            components["max_pain_dist_pct"] = round(pain_dist * 100, 2)
            pull = _clamp(abs(pain_dist) * 500, 0, 15)
            score_pts += pull
            if pain_dist > 0:
                direction_sum -= 0.1
            else:
                direction_sum += 0.1

        final = _clamp(score_pts)
        d = max(-1.0, min(1.0, direction_sum))
        return DimensionScore("gamma_leverage", final, d, components)


class _VolatilityEdgeScorer:
    """Dimension 4: IV surface analysis — rank, skew, RV spread, term structure."""

    @staticmethod
    def score(md: MarketData, hist: HistoricalData,
              ctx: ScanContext) -> DimensionScore:
        components: dict[str, float] = {}
        score_pts = 0.0
        direction_sum = 0.0

        opts = ctx.metadata.get("options_data", {}) if ctx else {}
        bars = hist.bars if hist else []

        # --- IV rank / percentile ---
        iv_rank = opts.get("iv_rank", 50.0)
        iv_pctl = opts.get("iv_percentile", 50.0)
        components["iv_rank"] = round(iv_rank, 1)
        components["iv_percentile"] = round(iv_pctl, 1)

        # Extremes are interesting: very low (cheap) or very high (mean-revert)
        if iv_rank < 15 or iv_rank > 85:
            score_pts += 20
        elif iv_rank < 30 or iv_rank > 70:
            score_pts += 12
        else:
            score_pts += 5

        # --- Skew z-score (put IV vs call IV) ---
        skew_z = opts.get("skew_zscore", 0.0)
        components["skew_zscore"] = round(skew_z, 2)
        if abs(skew_z) > 2.0:
            score_pts += 25
            direction_sum += -skew_z * 0.2
        elif abs(skew_z) > 1.0:
            score_pts += 15
            direction_sum += -skew_z * 0.1

        # --- IV vs Realized Vol spread ---
        if len(bars) >= 20:
            returns = []
            for i in range(1, len(bars)):
                if bars[i - 1].close > 0:
                    returns.append(math.log(bars[i].close / bars[i - 1].close))
            if len(returns) >= 10:
                rv = statistics.stdev(returns[-20:]) * math.sqrt(252) * 100
                iv = opts.get("atm_iv", rv)
                spread = iv - rv
                components["iv_rv_spread"] = round(spread, 2)
                components["realized_vol"] = round(rv, 2)
                if spread > 10:
                    score_pts += 18
                    direction_sum -= 0.1
                elif spread < -5:
                    score_pts += 15
                    direction_sum += 0.1
                else:
                    score_pts += 5
            else:
                components["iv_rv_spread"] = 0.0
        else:
            components["iv_rv_spread"] = 0.0

        # --- Term structure slope ---
        ts_slope = opts.get("term_structure_slope", 0.0)
        components["term_structure_slope"] = round(ts_slope, 3)
        if ts_slope < -0.05:
            score_pts += 15
        elif ts_slope > 0.05:
            score_pts += 8

        final = _clamp(score_pts)
        d = max(-1.0, min(1.0, direction_sum))
        return DimensionScore("volatility_edge", final, d, components)


class _MomentumConfluenceScorer:
    """Dimension 5: Multi-TF trend alignment, RSI divergence, MACD acceleration."""

    @staticmethod
    def score(md: MarketData, hist: HistoricalData,
              ctx: ScanContext) -> DimensionScore:
        components: dict[str, float] = {}
        score_pts = 0.0
        direction_sum = 0.0

        bars = hist.bars if hist else []
        closes = [b.close for b in bars] if bars else []
        highs = [b.high for b in bars] if bars else []
        lows = [b.low for b in bars] if bars else []

        if len(closes) < 30:
            return DimensionScore("momentum_confluence", 0.0, 0.0, {"insufficient_data": True})

        # --- RSI ---
        rsi = _rsi(closes)
        components["rsi"] = round(rsi, 1)
        if rsi > 70:
            score_pts += 12
            direction_sum += 0.3
        elif rsi < 30:
            score_pts += 12
            direction_sum -= 0.3
        elif rsi > 55:
            score_pts += 6
            direction_sum += 0.1
        elif rsi < 45:
            score_pts += 6
            direction_sum -= 0.1

        # --- MACD histogram acceleration ---
        macd_val, signal_val, histogram = _macd(closes)
        components["macd"] = round(macd_val, 4)
        components["macd_histogram"] = round(histogram, 4)

        if len(closes) >= 28:
            prev_hist = _macd(closes[:-1])[2]
            accel = histogram - prev_hist
            components["macd_accel"] = round(accel, 4)
            if accel > 0 and histogram > 0:
                score_pts += 15
                direction_sum += 0.25
            elif accel < 0 and histogram < 0:
                score_pts += 15
                direction_sum -= 0.25
            elif abs(accel) > abs(prev_hist) * 0.5:
                score_pts += 8

        # --- ADX trend strength ---
        adx_val, plus_di, minus_di = _adx(highs, lows, closes)
        components["adx"] = round(adx_val, 1)
        components["plus_di"] = round(plus_di, 1)
        components["minus_di"] = round(minus_di, 1)

        if adx_val > 30:
            score_pts += 15
        elif adx_val > 20:
            score_pts += 8

        if plus_di > minus_di:
            direction_sum += 0.2
        else:
            direction_sum -= 0.2

        # --- Multi-TF EMA alignment (9/21 EMA cross on different lookbacks) ---
        ema9 = _ema(closes, 9)[-1]
        ema21 = _ema(closes, 21)[-1]
        sma50 = sum(closes[-50:]) / min(50, len(closes)) if len(closes) >= 20 else closes[-1]

        aligned_bull = ema9 > ema21 > sma50
        aligned_bear = ema9 < ema21 < sma50
        components["ema9"] = round(ema9, 2)
        components["ema21"] = round(ema21, 2)
        components["sma50"] = round(sma50, 2)
        components["aligned"] = "bull" if aligned_bull else ("bear" if aligned_bear else "mixed")

        if aligned_bull:
            score_pts += 20
            direction_sum += 0.3
        elif aligned_bear:
            score_pts += 20
            direction_sum -= 0.3
        else:
            score_pts += 5

        # --- RSI divergence ---
        if len(closes) >= 20:
            price_lo = min(closes[-10:])
            price_lo_prev = min(closes[-20:-10])
            rsi_lo = _rsi(closes[-10:])
            rsi_lo_prev = _rsi(closes[-20:])

            if price_lo < price_lo_prev and rsi_lo > rsi_lo_prev:
                components["bullish_divergence"] = True
                score_pts += 12
                direction_sum += 0.2
            elif price_lo > price_lo_prev and rsi_lo < rsi_lo_prev:
                components["bearish_divergence"] = True
                score_pts += 12
                direction_sum -= 0.2

        final = _clamp(score_pts)
        d = max(-1.0, min(1.0, direction_sum))
        return DimensionScore("momentum_confluence", final, d, components)


class _VolumeProfileScorer:
    """Dimension 6: VWAP deviation, relative volume, POC analysis."""

    @staticmethod
    def score(md: MarketData, hist: HistoricalData,
              ctx: ScanContext) -> DimensionScore:
        components: dict[str, float] = {}
        score_pts = 0.0
        direction_sum = 0.0

        bars = hist.bars if hist else []
        if len(bars) < 10:
            return DimensionScore("volume_profile", 0.0, 0.0, {"insufficient_data": True})

        highs = [b.high for b in bars]
        lows = [b.low for b in bars]
        closes = [b.close for b in bars]
        volumes = [b.volume for b in bars]

        # --- VWAP deviation ---
        vwap_val = _vwap(highs, lows, closes, volumes)
        price = md.close

        cum_tp_vol = 0.0
        cum_vol = 0
        sq_sum = 0.0
        for h, l, c, v in zip(highs, lows, closes, volumes):
            tp = (h + l + c) / 3.0
            cum_tp_vol += tp * v
            cum_vol += v
            running_vwap = cum_tp_vol / cum_vol if cum_vol > 0 else tp
            sq_sum += v * (tp - running_vwap) ** 2
        vwap_std = math.sqrt(sq_sum / cum_vol) if cum_vol > 0 else 1.0

        sigma_dev = (price - vwap_val) / vwap_std if vwap_std > 1e-9 else 0.0
        components["vwap"] = round(vwap_val, 2)
        components["vwap_sigma"] = round(sigma_dev, 2)

        abs_dev = abs(sigma_dev)
        if abs_dev > 2.5:
            score_pts += 25
        elif abs_dev > 1.5:
            score_pts += 18
        elif abs_dev > 1.0:
            score_pts += 10
        else:
            score_pts += 3

        if sigma_dev > 0:
            direction_sum += min(0.3, sigma_dev * 0.1)
        else:
            direction_sum += max(-0.3, sigma_dev * 0.1)

        # --- Relative volume ---
        rv = md.relative_volume or 1.0
        components["relative_volume"] = round(rv, 2)
        if rv >= 3.0:
            score_pts += 25
        elif rv >= 2.0:
            score_pts += 18
        elif rv >= 1.5:
            score_pts += 10
        else:
            score_pts += 3

        # --- Volume-price trend (rising price + rising volume = conviction) ---
        if len(closes) >= 5 and len(volumes) >= 5:
            price_chg = (closes[-1] - closes[-5]) / closes[-5] if closes[-5] > 0 else 0.0
            vol_chg = (sum(volumes[-3:]) / 3) / (sum(volumes[-8:-3]) / 5) if sum(volumes[-8:-3]) > 0 else 1.0
            components["price_chg_5bar"] = round(price_chg * 100, 2)
            components["vol_trend"] = round(vol_chg, 2)

            if price_chg > 0 and vol_chg > 1.2:
                score_pts += 20
                direction_sum += 0.2
            elif price_chg < 0 and vol_chg > 1.2:
                score_pts += 20
                direction_sum -= 0.2
            elif vol_chg < 0.7:
                score_pts += 5

        # --- POC (Point of Control) — price level with most volume ---
        if len(bars) >= 10:
            price_vol: dict[float, int] = {}
            for b in bars[-30:]:
                bucket = round(b.close, 1)
                price_vol[bucket] = price_vol.get(bucket, 0) + b.volume
            if price_vol:
                poc = max(price_vol, key=price_vol.get)  # type: ignore[arg-type]
                components["poc"] = poc
                poc_dist = (price - poc) / price if price > 0 else 0.0
                components["poc_dist_pct"] = round(poc_dist * 100, 2)
                if abs(poc_dist) < 0.003:
                    score_pts += 15

        final = _clamp(score_pts)
        d = max(-1.0, min(1.0, direction_sum))
        return DimensionScore("volume_profile", final, d, components)


class _MarketRegimeScorer:
    """Dimension 7: Sector RS, SPY correlation, VIX regime, market internals."""

    @staticmethod
    def score(md: MarketData, hist: HistoricalData,
              ctx: ScanContext) -> DimensionScore:
        components: dict[str, float] = {}
        score_pts = 0.0
        direction_sum = 0.0

        regime = ctx.metadata.get("market_regime", {}) if ctx else {}

        # --- VIX level ---
        vix = regime.get("vix", 18.0)
        components["vix"] = round(vix, 2)
        if vix < 13:
            score_pts += 10
            direction_sum += 0.1
        elif vix < 20:
            score_pts += 15
        elif vix < 30:
            score_pts += 12
            direction_sum -= 0.1
        else:
            score_pts += 8
            direction_sum -= 0.2

        # --- NYSE TICK ---
        tick = regime.get("nyse_tick", 0)
        components["nyse_tick"] = tick
        if tick > 500:
            score_pts += 15
            direction_sum += 0.25
        elif tick > 200:
            score_pts += 10
            direction_sum += 0.1
        elif tick < -500:
            score_pts += 15
            direction_sum -= 0.25
        elif tick < -200:
            score_pts += 10
            direction_sum -= 0.1

        # --- TRIN (Arms Index) ---
        trin = regime.get("trin", 1.0)
        components["trin"] = round(trin, 3)
        if trin < 0.75:
            score_pts += 12
            direction_sum += 0.15
        elif trin > 1.5:
            score_pts += 12
            direction_sum -= 0.15

        # --- Sector relative strength ---
        sector_rs = regime.get("sector_relative_strength", 0.0)
        components["sector_rs"] = round(sector_rs, 2)
        if sector_rs > 1.5:
            score_pts += 15
            direction_sum += 0.2
        elif sector_rs > 0.5:
            score_pts += 8
            direction_sum += 0.1
        elif sector_rs < -1.5:
            score_pts += 15
            direction_sum -= 0.2
        elif sector_rs < -0.5:
            score_pts += 8
            direction_sum -= 0.1

        # --- SPY correlation (convergence/divergence) ---
        spy_corr = regime.get("spy_correlation", 0.8)
        components["spy_correlation"] = round(spy_corr, 2)
        if spy_corr < 0.3:
            score_pts += 20
        elif spy_corr > 0.9:
            score_pts += 5

        # --- Advance/Decline breadth ---
        ad_ratio = regime.get("ad_ratio", 1.0)
        components["ad_ratio"] = round(ad_ratio, 2)
        if ad_ratio > 2.0:
            score_pts += 12
            direction_sum += 0.15
        elif ad_ratio < 0.5:
            score_pts += 12
            direction_sum -= 0.15

        final = _clamp(score_pts)
        d = max(-1.0, min(1.0, direction_sum))
        return DimensionScore("market_regime", final, d, components)


class _StructuralSetupScorer:
    """Dimension 8: Key levels, FVG, order blocks, liquidity sweeps."""

    @staticmethod
    def score(md: MarketData, hist: HistoricalData,
              ctx: ScanContext) -> DimensionScore:
        components: dict[str, float] = {}
        score_pts = 0.0
        direction_sum = 0.0

        bars = hist.bars if hist else []
        if len(bars) < 20:
            return DimensionScore("structural_setup", 0.0, 0.0, {"insufficient_data": True})

        price = md.close
        highs = [b.high for b in bars]
        lows = [b.low for b in bars]
        closes = [b.close for b in bars]

        # --- Support / Resistance (swing highs/lows, 5-bar lookback) ---
        swing_highs: list[float] = []
        swing_lows: list[float] = []
        for i in range(5, len(bars) - 5):
            if all(highs[i] >= highs[j] for j in range(i - 5, i + 6) if j != i):
                swing_highs.append(highs[i])
            if all(lows[i] <= lows[j] for j in range(i - 5, i + 6) if j != i):
                swing_lows.append(lows[i])

        nearest_res = min((h for h in swing_highs if h > price), default=0.0)
        nearest_sup = max((l for l in swing_lows if l < price), default=0.0)

        if nearest_res > 0:
            res_dist = (nearest_res - price) / price
            components["resistance_dist_pct"] = round(res_dist * 100, 2)
            if res_dist < 0.005:
                score_pts += 15
                direction_sum -= 0.15
        if nearest_sup > 0:
            sup_dist = (price - nearest_sup) / price
            components["support_dist_pct"] = round(sup_dist * 100, 2)
            if sup_dist < 0.005:
                score_pts += 15
                direction_sum += 0.15

        # --- Fair Value Gaps (imbalance zones) ---
        fvg_count = 0
        for i in range(2, len(bars)):
            gap_up = bars[i].low > bars[i - 2].high
            gap_dn = bars[i].high < bars[i - 2].low
            if gap_up:
                gap_lo, gap_hi = bars[i - 2].high, bars[i].low
                if gap_lo <= price <= gap_hi:
                    fvg_count += 1
                    direction_sum += 0.1
            elif gap_dn:
                gap_lo, gap_hi = bars[i].high, bars[i - 2].low
                if gap_lo <= price <= gap_hi:
                    fvg_count += 1
                    direction_sum -= 0.1

        components["fvg_at_price"] = fvg_count
        score_pts += _clamp(fvg_count * 12, 0, 25)

        # --- Order blocks (strong impulse candle origins) ---
        atr = _atr(highs, lows, closes)
        ob_zones: list[tuple[float, float, str]] = []
        for i in range(1, len(bars)):
            body = abs(bars[i].close - bars[i].open)
            if body > 2.0 * atr and atr > 0:
                if bars[i].close > bars[i].open:
                    ob_zones.append((bars[i].low, bars[i].open, "bullish"))
                else:
                    ob_zones.append((bars[i].open, bars[i].high, "bearish"))

        ob_at_price = [ob for ob in ob_zones if ob[0] <= price <= ob[1]]
        components["order_blocks_at_price"] = len(ob_at_price)
        for ob in ob_at_price:
            score_pts += 12
            direction_sum += 0.15 if ob[2] == "bullish" else -0.15

        # --- Liquidity sweep detection (false breakout + reversal) ---
        if len(bars) >= 3:
            prev_high = max(highs[-20:-1]) if len(highs) > 20 else max(highs[:-1])
            prev_low = min(lows[-20:-1]) if len(lows) > 20 else min(lows[:-1])

            swept_high = bars[-2].high > prev_high and bars[-1].close < prev_high
            swept_low = bars[-2].low < prev_low and bars[-1].close > prev_low

            if swept_high:
                components["liquidity_sweep"] = "bearish"
                score_pts += 18
                direction_sum -= 0.25
            elif swept_low:
                components["liquidity_sweep"] = "bullish"
                score_pts += 18
                direction_sum += 0.25

        # --- Break of structure ---
        if len(swing_highs) >= 2 and len(swing_lows) >= 2:
            if swing_highs[-1] > swing_highs[-2] and swing_lows[-1] > swing_lows[-2]:
                components["structure"] = "bullish_bos"
                score_pts += 10
                direction_sum += 0.15
            elif swing_highs[-1] < swing_highs[-2] and swing_lows[-1] < swing_lows[-2]:
                components["structure"] = "bearish_bos"
                score_pts += 10
                direction_sum -= 0.15

        final = _clamp(score_pts)
        d = max(-1.0, min(1.0, direction_sum))
        return DimensionScore("structural_setup", final, d, components)


# ---------------------------------------------------------------------------
# Option contract selection
# ---------------------------------------------------------------------------

def _select_option(direction: SignalDirection, price: float, atr: float,
                   opts_data: dict) -> Optional[OptionRecommendation]:
    """Pick the optimal option contract for the trade."""
    if direction == SignalDirection.NEUTRAL:
        return None

    is_long = direction == SignalDirection.LONG
    opt_type = "CALL" if is_long else "PUT"

    iv_rank = opts_data.get("iv_rank", 50.0)

    # DTE selection: lower IV → buy shorter, higher IV → buy longer for edge
    if iv_rank < 25:
        dte = 3
        delta_target = 0.55
    elif iv_rank < 50:
        dte = 5
        delta_target = 0.50
    elif iv_rank < 75:
        dte = 7
        delta_target = 0.45
    else:
        dte = 10
        delta_target = 0.40

    # Strike selection: slight OTM for leverage, not too far for theta
    strike_offset = atr * 0.5
    if is_long:
        strike = round((price + strike_offset * 0.3) * 2) / 2
    else:
        strike = round((price - strike_offset * 0.3) * 2) / 2

    # Premium estimation (simplified Black-Scholes proxy)
    iv = opts_data.get("atm_iv", 30.0) / 100.0
    t = dte / 365.0
    premium = price * iv * math.sqrt(t) * 0.4
    premium = max(0.10, round(premium, 2))

    # Breakeven
    if is_long:
        breakeven = strike + premium
    else:
        breakeven = strike - premium

    # Expected PnL
    target_move = atr * 1.5
    if is_long:
        target_pnl_pct = (target_move / premium) * delta_target * 100
    else:
        target_pnl_pct = (target_move / premium) * delta_target * 100

    return OptionRecommendation(
        option_type=opt_type,
        strike=strike,
        expiry_days=dte,
        delta=delta_target if is_long else -delta_target,
        estimated_premium=premium,
        breakeven=round(breakeven, 2),
        max_risk=premium,
        target_pnl_pct=round(min(target_pnl_pct, 500.0), 1),
        greeks={
            "delta": delta_target if is_long else -delta_target,
            "gamma": round(0.05 / (iv * math.sqrt(t) * price) if t > 0 else 0, 4),
            "theta": round(-premium / dte if dte > 0 else 0, 4),
            "vega": round(price * math.sqrt(t) * 0.01, 4),
        },
    )


# ---------------------------------------------------------------------------
# Regime detection
# ---------------------------------------------------------------------------

def _detect_regime(ctx: ScanContext, hist: HistoricalData) -> tuple[str, list[float]]:
    """Classify current regime and return adaptive weights."""
    regime_data = ctx.metadata.get("market_regime", {}) if ctx else {}
    vix = regime_data.get("vix", 18.0)

    bars = hist.bars if hist else []
    closes = [b.close for b in bars] if bars else []

    # Trend detection via ADX
    trending = False
    if len(closes) >= 20:
        highs = [b.high for b in bars]
        lows = [b.low for b in bars]
        adx_val, _, _ = _adx(highs, lows, closes)
        trending = adx_val > 25

    # Mean-reversion detection via Bollinger squeeze
    mean_rev = False
    if len(closes) >= 20:
        sma = sum(closes[-20:]) / 20
        std = statistics.stdev(closes[-20:])
        bb_width = (2 * std) / sma if sma > 0 else 0
        mean_rev = bb_width < 0.03

    if vix > 28:
        return "high_volatility", WEIGHTS_HIGH_VOL
    elif vix < 13:
        return "low_volatility", WEIGHTS_LOW_VOL
    elif trending:
        return "trending", WEIGHTS_TRENDING
    elif mean_rev:
        return "mean_reversion", WEIGHTS_MEAN_REV
    else:
        return "normal", WEIGHTS_NORMAL


# ---------------------------------------------------------------------------
# Main scanner
# ---------------------------------------------------------------------------

SCORERS = [
    _TapePressureScorer,
    _OptionsCatalystScorer,
    _GammaLeverageScorer,
    _VolatilityEdgeScorer,
    _MomentumConfluenceScorer,
    _VolumeProfileScorer,
    _MarketRegimeScorer,
    _StructuralSetupScorer,
]


class PrecisionAlphaScanner(BaseScanner):
    """
    Unified day-trading & scalping scanner for optionable stocks.

    Scores every symbol across 8 orthogonal dimensions, regime-adapts the
    weights, and outputs an actionable trade with optimal option selection.
    """

    name = "precision_alpha"
    description = "8-dimension composite alpha for intraday scalping of optionable stocks"

    def __init__(self, config: Optional[ScannerConfig] = None):
        super().__init__(
            name="precision_alpha",
            scan_mode=ScanMode.ALL,
            config=config or ScannerConfig(),
        )

    def validate_signal(self, result: ScanResult, context: ScanContext) -> bool:
        return result.confidence >= SIGNAL_THRESHOLD and result.direction != SignalDirection.NEUTRAL

    async def scan(self, context: ScanContext) -> list[ScanResult]:
        results: list[ScanResult] = []

        for symbol in context.universe:
            try:
                result = await self._score_symbol(symbol, context)
                if result and result.confidence >= SIGNAL_THRESHOLD:
                    results.append(self._to_scan_result(result))
            except Exception:
                logger.exception("PrecisionAlpha error on %s", symbol)

        results.sort(key=lambda r: r.confidence, reverse=True)
        return results

    async def _score_symbol(
        self, symbol: str, context: ScanContext
    ) -> Optional[PrecisionAlphaResult]:
        md = self._get_market_data(symbol, context)
        hist = self._get_historical(symbol, context)
        if md is None or md.close <= 0:
            return None

        regime_name, weights = _detect_regime(context, hist)

        dimensions: list[DimensionScore] = []
        for scorer in SCORERS:
            dim = scorer.score(md, hist, context)
            dimensions.append(dim)

        weighted_score = sum(
            d.score * w for d, w in zip(dimensions, weights)
        )
        composite = _clamp(weighted_score)

        direction_votes = sum(d.direction * w for d, w in zip(dimensions, weights))
        if direction_votes > 0.08:
            direction = SignalDirection.LONG
        elif direction_votes < -0.08:
            direction = SignalDirection.SHORT
        else:
            direction = SignalDirection.NEUTRAL

        # Confluence bonus: if ≥6 dimensions agree on direction, boost score
        agreeing = sum(
            1 for d in dimensions
            if (d.direction > 0.05 and direction == SignalDirection.LONG)
            or (d.direction < -0.05 and direction == SignalDirection.SHORT)
        )
        if agreeing >= 6:
            composite = _clamp(composite * 1.10)
        elif agreeing >= 5:
            composite = _clamp(composite * 1.05)

        # Opposing penalty: if any strong dimension opposes, dampen
        opposing = sum(
            1 for d in dimensions
            if d.score > 60
            and (
                (d.direction < -0.1 and direction == SignalDirection.LONG)
                or (d.direction > 0.1 and direction == SignalDirection.SHORT)
            )
        )
        if opposing >= 2:
            composite *= 0.85

        bars = hist.bars if hist else []
        closes = [b.close for b in bars] if bars else [md.close]
        highs = [b.high for b in bars] if bars else [md.high]
        lows = [b.low for b in bars] if bars else [md.low]
        atr = _atr(highs, lows, closes)

        entry = md.close
        if direction == SignalDirection.LONG:
            stop = round(entry - 2.0 * atr, 2)
            targets = [
                round(entry + 1.5 * atr, 2),
                round(entry + 2.5 * atr, 2),
                round(entry + 4.0 * atr, 2),
            ]
        elif direction == SignalDirection.SHORT:
            stop = round(entry + 2.0 * atr, 2)
            targets = [
                round(entry - 1.5 * atr, 2),
                round(entry - 2.5 * atr, 2),
                round(entry - 4.0 * atr, 2),
            ]
        else:
            stop = round(entry - 1.5 * atr, 2)
            targets = []

        risk = abs(entry - stop)
        reward = abs(targets[0] - entry) if targets else 0.0
        rr = round(reward / risk, 2) if risk > 0 else 0.0

        opts_data = context.metadata.get("options_data", {}) if context else {}
        option_rec = _select_option(direction, entry, atr, opts_data)

        return PrecisionAlphaResult(
            symbol=symbol,
            composite_score=round(composite, 2),
            direction=direction,
            confidence=round(composite, 2),
            dimensions=dimensions,
            entry_price=entry,
            stop_loss=stop,
            targets=targets,
            risk_reward=rr,
            option_rec=option_rec,
            regime=regime_name,
            weights_used=[round(w, 3) for w in weights],
            timestamp=datetime.now(timezone.utc),
        )

    def _to_scan_result(self, pa: PrecisionAlphaResult) -> ScanResult:
        meta: dict[str, Any] = {
            "regime": pa.regime,
            "weights": pa.weights_used,
            "dimensions": {
                d.name: {
                    "score": round(d.score, 1),
                    "direction": round(d.direction, 3),
                    "components": d.components,
                }
                for d in pa.dimensions
            },
        }
        if pa.option_rec:
            meta["option_recommendation"] = {
                "type": pa.option_rec.option_type,
                "strike": pa.option_rec.strike,
                "dte": pa.option_rec.expiry_days,
                "delta": pa.option_rec.delta,
                "premium": pa.option_rec.estimated_premium,
                "breakeven": pa.option_rec.breakeven,
                "max_risk": pa.option_rec.max_risk,
                "target_pnl_pct": pa.option_rec.target_pnl_pct,
                "greeks": pa.option_rec.greeks,
            }

        return ScanResult(
            symbol=pa.symbol,
            scanner_type="precision_alpha",
            direction=pa.direction,
            confidence=pa.confidence,
            entry_price=pa.entry_price,
            stop_loss=pa.stop_loss,
            targets=pa.targets,
            risk_reward=pa.risk_reward,
            timeframe=TimeFrame.M1,
            metadata=meta,
        )

    # --- Data helpers ---

    @staticmethod
    def _get_market_data(symbol: str, ctx: ScanContext) -> Optional[MarketData]:
        if ctx.market_data and symbol in ctx.market_data:
            return ctx.market_data[symbol]
        if ctx.market_data:
            for key, val in ctx.market_data.items():
                if key.upper() == symbol.upper():
                    return val
        return None

    @staticmethod
    def _get_historical(symbol: str, ctx: ScanContext) -> HistoricalData:
        if ctx.historical_data and symbol in ctx.historical_data:
            return ctx.historical_data[symbol]
        return HistoricalData(bars=[])
