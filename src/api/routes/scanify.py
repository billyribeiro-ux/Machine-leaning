"""
SCANIFY 0DTE SPX Scanner API Routes

Real-time API endpoints for the SCANIFY SPX 0DTE options day trading scanner
system.  Provides access to scanner control, GEX data, scan signals, positions,
session/market data, calibration state, and dashboard data packages.

All endpoints use the ``/api/scanify`` prefix and follow the project's
established patterns for authentication, response models, and error handling.
"""

import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from src.api.auth.jwt import (
    get_current_active_user,
    get_optional_user,
    require_tier,
    User,
)
from src.api.auth.tiers import SubscriptionTier

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/scanify", tags=["scanify"])


# =============================================================================
# Module-level orchestrator reference
# =============================================================================

_orchestrator = None


def set_orchestrator(orchestrator) -> None:
    """Set the ScanifyOrchestrator instance (called from main app startup)."""
    global _orchestrator
    _orchestrator = orchestrator


def _get_orchestrator():
    """Return the orchestrator or raise 503 if not available."""
    if _orchestrator is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SCANIFY system is not initialized. Start the scanner first.",
        )
    return _orchestrator


# =============================================================================
# RESPONSE MODELS -- Scanner Status & Control
# =============================================================================


class ScanifyHealthResponse(BaseModel):
    """Health check response for the SCANIFY system."""

    status: str = Field(..., description="healthy, degraded, or down")
    is_running: bool = Field(..., description="Whether the scanner is actively running")
    data_connected: bool = Field(..., description="Whether data feeds are connected")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Health check timestamp",
    )


class ScanifyStatusResponse(BaseModel):
    """Full scanner system status."""

    is_running: bool = Field(..., description="Whether the scanner loop is active")
    session_type: str = Field(..., description="Detected session regime (TRENDING, RANGE, etc.)")
    time_zone: str = Field(..., description="Current intraday time zone bucket")
    scan_count: int = Field(..., ge=0, description="Total scan cycles completed today")
    last_scan_time: Optional[str] = Field(None, description="ISO timestamp of last scan")
    active_positions: int = Field(..., ge=0, description="Number of open positions")
    total_pnl: float = Field(..., description="Combined realized + unrealized P&L ($)")
    realized_pnl: float = Field(..., description="Realized P&L ($)")
    unrealized_pnl: float = Field(..., description="Unrealized P&L ($)")
    paper_trade: bool = Field(..., description="Whether running in paper-trade mode")
    data_connected: bool = Field(..., description="Data feed connection status")
    risk_budget_remaining: float = Field(..., ge=0, description="Remaining risk budget ($)")
    minutes_remaining: int = Field(..., description="Minutes until market close")
    recent_alerts: List[Dict[str, Any]] = Field(
        default_factory=list, description="Last 20 system alerts"
    )


class ScanifyControlResponse(BaseModel):
    """Response for start/stop control actions."""

    action: str = Field(..., description="Action performed (start or stop)")
    success: bool = Field(..., description="Whether the action succeeded")
    message: str = Field(..., description="Human-readable status message")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Action timestamp",
    )


# =============================================================================
# RESPONSE MODELS -- GEX Data
# =============================================================================


class StrikeGEXResponse(BaseModel):
    """Per-strike gamma exposure data point."""

    strike: float = Field(..., description="Strike price")
    call_gamma: float = Field(..., description="Call gamma at this strike")
    put_gamma: float = Field(..., description="Put gamma at this strike")
    call_oi: int = Field(..., ge=0, description="Call open interest")
    put_oi: int = Field(..., ge=0, description="Put open interest")
    net_gex: float = Field(..., description="Net dealer gamma exposure at strike")
    net_charm: float = Field(..., description="Net charm exposure at strike")
    net_vanna: float = Field(..., description="Net vanna exposure at strike")


class GEXProfileResponse(BaseModel):
    """Complete GEX profile across all strikes."""

    timestamp: datetime = Field(..., description="Profile computation time")
    strikes: List[StrikeGEXResponse] = Field(
        default_factory=list, description="Per-strike GEX breakdown"
    )
    total_net_gex: float = Field(..., description="Aggregate net GEX")
    gamma_flip_level: float = Field(..., description="Gamma flip crossover price")
    call_wall: float = Field(..., description="Largest call gamma strike (resistance)")
    put_wall: float = Field(..., description="Largest put gamma strike (support)")
    max_pain: float = Field(..., description="Max pain strike")
    vol_trigger: float = Field(..., description="Vol trigger level")
    gex_momentum: float = Field(0.0, description="Rate of change in total net GEX")
    is_positive_gamma: bool = Field(..., description="True if above gamma flip")


class GEXSignalResponse(BaseModel):
    """Individual GEX-derived signal."""

    signal_type: str = Field(..., description="GEX signal category")
    direction: str = Field(..., description="Implied directional bias")
    confidence: float = Field(..., ge=0, le=100, description="Confidence score (0-100)")
    description: str = Field(..., description="Human-readable signal narrative")
    trigger_price: float = Field(..., description="Price that activated signal")
    target_price: Optional[float] = Field(None, description="Expected target price")
    timestamp: datetime = Field(..., description="Signal generation time")


class GEXLevelsResponse(BaseModel):
    """Key GEX-derived price levels."""

    gamma_flip: float = Field(..., description="Gamma flip level")
    call_wall: float = Field(..., description="Largest call gamma strike")
    put_wall: float = Field(..., description="Largest put gamma strike")
    max_pain: float = Field(..., description="Max pain strike")
    plus_gex: float = Field(..., description="Highest positive net GEX strike")
    minus_gex: float = Field(..., description="Most negative net GEX strike")
    vol_trigger: float = Field(..., description="Vol trigger level")
    transition_zone_upper: float = Field(..., description="Upper transition zone bound")
    transition_zone_lower: float = Field(..., description="Lower transition zone bound")
    is_positive_gamma_regime: bool = Field(
        ..., description="Market is in positive gamma territory"
    )


class GEXHistoryEntry(BaseModel):
    """Single GEX profile history point for charting."""

    timestamp: datetime = Field(..., description="Profile computation time")
    total_net_gex: float = Field(..., description="Aggregate net GEX at this time")
    gamma_flip_level: float = Field(..., description="Gamma flip level")
    call_wall: float = Field(..., description="Call wall strike")
    put_wall: float = Field(..., description="Put wall strike")


class GEXHistoryResponse(BaseModel):
    """GEX profile history for charting."""

    entries: List[GEXHistoryEntry] = Field(
        default_factory=list, description="Chronological GEX snapshots"
    )
    count: int = Field(..., ge=0, description="Number of history entries")


# =============================================================================
# RESPONSE MODELS -- Scanner Signals
# =============================================================================


class DirectionScoreResponse(BaseModel):
    """Composite directional scoring breakdown."""

    total_score: float = Field(..., description="Net composite direction score (-100..+100)")
    market_internals_score: float = Field(..., description="NYSE breadth sub-score")
    options_flow_score: float = Field(..., description="Options flow sub-score")
    price_action_score: float = Field(..., description="Price-action sub-score")
    gex_structure_score: float = Field(..., description="GEX structure sub-score")
    cross_asset_score: float = Field(..., description="Cross-asset sub-score")
    factors_agreeing: int = Field(..., ge=0, le=5, description="Aligned sub-scores count")
    signal: str = Field(..., description="Discrete directional signal (BULL/BEAR/NEUTRAL)")
    confidence: float = Field(..., ge=0, le=100, description="Confidence (0-100)")


class ScanSignalResponse(BaseModel):
    """Single scan signal / trade recommendation."""

    scan_type: str = Field(..., description="Strategy archetype (DIRECTIONAL, PREMIUM_SELL, GAMMA_SCALP)")
    direction: str = Field(..., description="Directional bias (BULL/BEAR/NEUTRAL)")
    entry_price: float = Field(..., gt=0, description="Recommended entry price")
    stop_loss: float = Field(..., ge=0, description="Recommended stop-loss")
    profit_target: float = Field(..., gt=0, description="Recommended profit target")
    position_type: str = Field(..., description="Position structure")
    contracts: int = Field(..., ge=1, description="Recommended contracts")
    max_risk: float = Field(..., ge=0, description="Maximum dollar risk")
    expected_reward: float = Field(..., ge=0, description="Expected dollar reward")
    risk_reward_ratio: float = Field(..., gt=0, description="Reward/Risk ratio")
    time_zone: str = Field(..., description="Intraday time-zone bucket at signal time")
    session_type: str = Field(..., description="Session regime at signal time")
    direction_score: Optional[DirectionScoreResponse] = Field(
        None, description="Full direction scoring breakdown"
    )
    timestamp: datetime = Field(..., description="Signal generation time")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional signal data")


class SignalListResponse(BaseModel):
    """List of scan signals."""

    signals: List[ScanSignalResponse] = Field(
        default_factory=list, description="Scan signals"
    )
    total: int = Field(..., ge=0, description="Total signal count")
    scan_types: List[str] = Field(
        default_factory=list, description="Scan types present in results"
    )


class SignalHistoryResponse(BaseModel):
    """Signal history for the trading day."""

    signals: List[ScanSignalResponse] = Field(
        default_factory=list, description="All signals generated today"
    )
    total: int = Field(..., ge=0, description="Total signals today")
    by_type: Dict[str, int] = Field(
        default_factory=dict, description="Signal count by scan type"
    )
    by_direction: Dict[str, int] = Field(
        default_factory=dict, description="Signal count by direction"
    )


# =============================================================================
# RESPONSE MODELS -- Positions & Trades
# =============================================================================


class PositionResponse(BaseModel):
    """Active position detail."""

    signal_id: str = Field(..., description="Unique signal/position ID")
    direction: str = Field(..., description="Trade direction")
    strategy: str = Field(..., description="Strategy type")
    entry_price: float = Field(..., description="Entry fill price")
    stop_loss: float = Field(0.0, description="Stop-loss price")
    take_profit: float = Field(0.0, description="Take-profit price")
    size: int = Field(..., ge=1, description="Number of contracts")
    pnl: float = Field(0.0, description="Current unrealized P&L ($)")
    max_pnl: float = Field(0.0, description="Peak unrealized P&L ($)")
    entry_time: str = Field(..., description="Entry timestamp (ISO)")
    status: str = Field(..., description="Position status (OPEN, CLOSED)")
    paper_trade: bool = Field(True, description="Paper trade flag")


class PositionListResponse(BaseModel):
    """List of active positions."""

    positions: List[PositionResponse] = Field(
        default_factory=list, description="Active positions"
    )
    total: int = Field(..., ge=0, description="Total active positions")
    total_unrealized_pnl: float = Field(0.0, description="Combined unrealized P&L ($)")


class TradeLogEntry(BaseModel):
    """Completed trade record."""

    signal_id: str = Field(..., description="Position/signal ID")
    direction: str = Field(..., description="Trade direction")
    strategy: str = Field(..., description="Strategy type")
    entry_price: float = Field(..., description="Entry fill price")
    exit_price: Optional[float] = Field(None, description="Exit fill price")
    pnl: float = Field(0.0, description="Realized P&L ($)")
    entry_time: str = Field(..., description="Entry timestamp")
    exit_time: Optional[str] = Field(None, description="Exit timestamp")
    exit_reason: Optional[str] = Field(None, description="Reason for exit")


class TradeLogResponse(BaseModel):
    """Trade log for a given period."""

    trades: List[TradeLogEntry] = Field(
        default_factory=list, description="Completed trades"
    )
    total: int = Field(..., ge=0, description="Total completed trades")
    winning: int = Field(0, ge=0, description="Winning trade count")
    losing: int = Field(0, ge=0, description="Losing trade count")


class PnLSummaryResponse(BaseModel):
    """Daily P&L summary."""

    date: str = Field(..., description="Trading date (ISO)")
    total_pnl: float = Field(..., description="Total P&L ($)")
    realized_pnl: float = Field(..., description="Realized P&L ($)")
    unrealized_pnl: float = Field(..., description="Unrealized P&L ($)")
    total_trades: int = Field(..., ge=0, description="Total trades today")
    winning_trades: int = Field(0, ge=0, description="Winning trades")
    losing_trades: int = Field(0, ge=0, description="Losing trades")
    win_rate: float = Field(0.0, ge=0, le=1.0, description="Win rate (0-1)")
    avg_win: float = Field(0.0, description="Average winning trade P&L ($)")
    avg_loss: float = Field(0.0, description="Average losing trade P&L ($)")
    profit_factor: float = Field(0.0, ge=0, description="Gross profit / gross loss")
    max_drawdown: float = Field(0.0, description="Maximum drawdown ($)")


# =============================================================================
# RESPONSE MODELS -- Session & Market Data
# =============================================================================


class GapAnalysisResponse(BaseModel):
    """Overnight gap analysis."""

    gap_pct: float = Field(..., description="Gap as % of prior close")
    gap_points: float = Field(..., description="Gap in SPX points")
    gap_sigma: float = Field(..., description="Gap in sigma units")
    classification: str = Field(..., description="MICRO/SMALL/MEDIUM/LARGE/MEGA")
    gap_fill_probability: Dict[str, float] = Field(
        default_factory=dict, description="Fill probability by time horizon"
    )


class ExpectedMoveResponse(BaseModel):
    """Expected move boundaries for the session."""

    method1_vix1d: float = Field(..., description="Expected move from VIX1D")
    method2_straddle: float = Field(..., description="Expected move from ATM straddle")
    method3_rv_adjusted: float = Field(..., description="Expected move from realized vol")
    final_1sigma: float = Field(..., description="Blended 1-sigma move (points)")
    final_2sigma: float = Field(..., description="Blended 2-sigma move (points)")
    iv_rv_ratio: float = Field(..., description="IV / RV ratio")
    vol_regime: str = Field(..., description="Vol regime label")


class KeyLevelsResponse(BaseModel):
    """Consolidated key price levels."""

    # GEX-derived
    gamma_flip: float = Field(..., description="Gamma flip level")
    call_wall: float = Field(..., description="Largest call gamma strike")
    put_wall: float = Field(..., description="Largest put gamma strike")
    max_pain: float = Field(..., description="Max pain strike")
    vol_trigger: float = Field(..., description="Vol trigger level")
    transition_zone_upper: float = Field(..., description="Upper transition bound")
    transition_zone_lower: float = Field(..., description="Lower transition bound")
    # Prior session
    prior_high: float = Field(..., description="Prior session high")
    prior_low: float = Field(..., description="Prior session low")
    prior_close: float = Field(..., description="Prior session close")
    # Overnight
    overnight_high: float = Field(..., description="Overnight high")
    overnight_low: float = Field(..., description="Overnight low")
    # Technical
    round_levels: List[float] = Field(default_factory=list, description="Round numbers")
    moving_averages: Dict[str, float] = Field(
        default_factory=dict, description="Key moving averages"
    )


class SessionSetupResponse(BaseModel):
    """Session setup from pre-market analysis."""

    session_type: str = Field(..., description="Predicted session regime")
    gap_analysis: GapAnalysisResponse = Field(..., description="Gap analysis")
    expected_move: ExpectedMoveResponse = Field(..., description="Expected move")
    risk_assessment: str = Field(..., description="Pre-market risk commentary")
    has_high_impact_events: bool = Field(
        False, description="Whether high-impact events are scheduled"
    )
    event_count: int = Field(0, ge=0, description="Number of economic events")
    timestamp: datetime = Field(..., description="Setup generation time")


class MarketInternalsResponse(BaseModel):
    """Current market internals snapshot."""

    nyse_tick: int = Field(..., description="NYSE TICK (instantaneous)")
    nyse_tick_10min_avg: float = Field(..., description="10-min TICK rolling average")
    cumulative_tick: float = Field(..., description="Session cumulative TICK")
    nyse_trin: float = Field(..., description="NYSE TRIN (Arms Index)")
    advance_decline_ratio: float = Field(..., description="Advancers / Decliners ratio")
    up_down_volume_ratio: float = Field(..., description="Up volume / Down volume ratio")
    es_cumulative_delta: float = Field(..., description="ES cumulative delta")
    tick_is_extreme_bullish: bool = Field(False, description="TICK above +800")
    tick_is_extreme_bearish: bool = Field(False, description="TICK below -800")
    trin_bullish: bool = Field(False, description="TRIN below 0.80")
    trin_bearish: bool = Field(False, description="TRIN above 1.20")
    timestamp: datetime = Field(..., description="Snapshot time")


# =============================================================================
# RESPONSE MODELS -- Calibration
# =============================================================================


class FactorWeightsResponse(BaseModel):
    """Current factor weights for the direction scorer."""

    market_internals: float = Field(..., ge=0, le=1.0, description="NYSE breadth weight")
    options_flow: float = Field(..., ge=0, le=1.0, description="Options flow weight")
    price_action: float = Field(..., ge=0, le=1.0, description="Price-action weight")
    gex_structure: float = Field(..., ge=0, le=1.0, description="GEX structure weight")
    cross_asset: float = Field(..., ge=0, le=1.0, description="Cross-asset weight")


class CalibrationStateResponse(BaseModel):
    """Current calibration state."""

    current_weights: FactorWeightsResponse = Field(
        ..., description="Active factor weights"
    )
    entry_threshold: float = Field(
        ..., ge=0, le=100, description="Minimum score to trigger trade"
    )
    stop_loss_pct: float = Field(..., description="Default stop-loss percentage")
    regime: str = Field(..., description="Current VIX/vol regime label")
    last_calibration: datetime = Field(..., description="Last calibration timestamp")
    trade_count: int = Field(..., ge=0, description="Trades since last calibration")
    gex_signal_accuracy: float = Field(
        ..., ge=0, le=1.0, description="Rolling GEX signal accuracy"
    )
    profit_targets_by_zone: Dict[str, float] = Field(
        default_factory=dict, description="Profit target by time zone"
    )


class DailyScorecardResponse(BaseModel):
    """Daily performance scorecard."""

    trading_date: str = Field(..., description="Trading date (ISO)")
    win_rate_by_scan_type: Dict[str, float] = Field(
        default_factory=dict, description="Win rate by strategy"
    )
    win_rate_by_time_zone: Dict[str, float] = Field(
        default_factory=dict, description="Win rate by time zone"
    )
    win_rate_by_session_type: Dict[str, float] = Field(
        default_factory=dict, description="Win rate by session type"
    )
    avg_pnl_by_category: Dict[str, float] = Field(
        default_factory=dict, description="Average P&L by category"
    )
    sharpe_ratio_by_scan: Dict[str, float] = Field(
        default_factory=dict, description="Sharpe ratio by strategy"
    )
    max_drawdown_by_scan: Dict[str, float] = Field(
        default_factory=dict, description="Max drawdown by strategy"
    )


class CalibrationRunResponse(BaseModel):
    """Result of a manual calibration run."""

    success: bool = Field(..., description="Whether calibration succeeded")
    summary: str = Field(..., description="Calibration result summary")
    adjustments: Dict[str, Any] = Field(
        default_factory=dict, description="Weight and threshold adjustments made"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Calibration run time",
    )


# =============================================================================
# RESPONSE MODELS -- Dashboard
# =============================================================================


class DashboardResponse(BaseModel):
    """Complete dashboard data package."""

    spx_price: float = Field(..., description="Current SPX price")
    status: ScanifyStatusResponse = Field(..., description="System status")
    expected_move: Dict[str, Any] = Field(
        default_factory=dict, description="Expected move boundaries"
    )
    gex_profile: Dict[str, Any] = Field(
        default_factory=dict, description="GEX chart summary"
    )
    key_levels: Dict[str, Any] = Field(
        default_factory=dict, description="Key price levels"
    )
    active_positions: List[Dict[str, Any]] = Field(
        default_factory=list, description="Active positions"
    )
    direction_score: Dict[str, Any] = Field(
        default_factory=dict, description="Direction scoring breakdown"
    )
    recent_signals: List[Dict[str, Any]] = Field(
        default_factory=list, description="Recent scan signals"
    )
    gex_signals: List[Dict[str, Any]] = Field(
        default_factory=list, description="Recent GEX signals"
    )
    intraday_pnl_curve: List[Dict[str, Any]] = Field(
        default_factory=list, description="Intraday P&L curve points"
    )
    session_classification: Dict[str, Any] = Field(
        default_factory=dict, description="Session classification info"
    )


class GEXChartDataResponse(BaseModel):
    """GEX bar chart data for the dashboard."""

    strikes: List[float] = Field(default_factory=list, description="Strike prices")
    net_gex_values: List[float] = Field(
        default_factory=list, description="Net GEX at each strike"
    )
    call_gamma_values: List[float] = Field(
        default_factory=list, description="Call gamma at each strike"
    )
    put_gamma_values: List[float] = Field(
        default_factory=list, description="Put gamma at each strike"
    )
    gamma_flip_level: float = Field(0.0, description="Gamma flip level")
    call_wall: float = Field(0.0, description="Call wall strike")
    put_wall: float = Field(0.0, description="Put wall strike")
    spx_price: float = Field(0.0, description="Current SPX price")


class DirectionScoreBreakdownResponse(BaseModel):
    """Direction score breakdown for dashboard widget."""

    total_score: float = Field(0.0, description="Net composite score")
    components: Dict[str, float] = Field(
        default_factory=dict, description="Individual factor scores"
    )
    signal: str = Field("NEUTRAL", description="Discrete directional signal")
    confidence: float = Field(0.0, description="Confidence (0-100)")
    factors_agreeing: int = Field(0, description="Aligned factors count")


class PnLCurveResponse(BaseModel):
    """Intraday P&L curve for charting."""

    points: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Timestamped P&L points [{timestamp, pnl, realized, unrealized}]",
    )
    current_pnl: float = Field(0.0, description="Current total P&L ($)")
    max_pnl: float = Field(0.0, description="Peak P&L ($)")
    min_pnl: float = Field(0.0, description="Trough P&L ($)")


# =============================================================================
# HELPERS -- Signal serialization
# =============================================================================


def _serialize_scan_signal(sig) -> dict:
    """Convert a ScanSignal model instance to a response-friendly dict."""
    direction_score_data = None
    ds = getattr(sig, "direction_score", None)
    if ds is not None:
        direction_score_data = {
            "total_score": getattr(ds, "total_score", 0.0),
            "market_internals_score": getattr(ds, "market_internals_score", 0.0),
            "options_flow_score": getattr(ds, "options_flow_score", 0.0),
            "price_action_score": getattr(ds, "price_action_score", 0.0),
            "gex_structure_score": getattr(ds, "gex_structure_score", 0.0),
            "cross_asset_score": getattr(ds, "cross_asset_score", 0.0),
            "factors_agreeing": getattr(ds, "factors_agreeing", 0),
            "signal": str(getattr(ds, "signal", "NEUTRAL")),
            "confidence": getattr(ds, "confidence", 0.0),
        }

    scan_type = getattr(sig, "scan_type", "UNKNOWN")
    direction = getattr(sig, "direction", "UNKNOWN")

    return {
        "scan_type": scan_type.value if hasattr(scan_type, "value") else str(scan_type),
        "direction": direction.value if hasattr(direction, "value") else str(direction),
        "entry_price": getattr(sig, "entry_price", 0.0),
        "stop_loss": getattr(sig, "stop_loss", 0.0),
        "profit_target": getattr(sig, "profit_target", 0.0),
        "position_type": str(getattr(sig, "position_type", "SINGLE_LONG")),
        "contracts": getattr(sig, "contracts", 1),
        "max_risk": getattr(sig, "max_risk", 0.0),
        "expected_reward": getattr(sig, "expected_reward", 0.0),
        "risk_reward_ratio": getattr(sig, "risk_reward_ratio", 0.0),
        "time_zone": str(getattr(sig, "time_zone", "UNKNOWN")),
        "session_type": str(getattr(sig, "session_type", "UNKNOWN")),
        "direction_score": direction_score_data,
        "timestamp": getattr(sig, "timestamp", datetime.now(timezone.utc)),
        "metadata": getattr(sig, "metadata", {}),
    }


def _serialize_position(pos: dict) -> dict:
    """Convert an active position dict to a response-friendly dict."""
    return {
        "signal_id": pos.get("signal_id", ""),
        "direction": pos.get("direction", ""),
        "strategy": pos.get("strategy", ""),
        "entry_price": pos.get("entry_price", 0.0),
        "stop_loss": pos.get("stop_loss", 0.0),
        "take_profit": pos.get("take_profit", 0.0),
        "size": pos.get("size", 1),
        "pnl": pos.get("pnl", 0.0),
        "max_pnl": pos.get("max_pnl", 0.0),
        "entry_time": pos.get("entry_time", ""),
        "status": pos.get("status", "OPEN"),
        "paper_trade": pos.get("paper_trade", True),
    }


def _serialize_trade(trade: dict) -> dict:
    """Convert a closed trade dict to a response-friendly dict."""
    return {
        "signal_id": trade.get("signal_id", ""),
        "direction": trade.get("direction", ""),
        "strategy": trade.get("strategy", ""),
        "entry_price": trade.get("entry_price", 0.0),
        "exit_price": trade.get("exit_price"),
        "pnl": trade.get("pnl", 0.0),
        "entry_time": trade.get("entry_time", ""),
        "exit_time": trade.get("exit_time"),
        "exit_reason": trade.get("exit_reason"),
    }


# =============================================================================
# 1. SCANNER STATUS & CONTROL
# =============================================================================


@router.get("/status", response_model=ScanifyStatusResponse)
async def get_scanner_status(
    current_user: User = Depends(get_current_active_user),
):
    """
    Get full SCANIFY scanner system status.

    Returns running state, session type, time zone, scan count, P&L,
    active positions, and recent alerts.  Requires authentication.
    """
    orch = _get_orchestrator()

    try:
        status_data = orch.get_status()
    except Exception as exc:
        logger.exception("Error getting scanner status: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve scanner status",
        ) from exc

    return ScanifyStatusResponse(
        is_running=status_data.get("is_running", False),
        session_type=status_data.get("session_type", "UNKNOWN"),
        time_zone=status_data.get("time_zone", "UNKNOWN"),
        scan_count=status_data.get("scan_count", 0),
        last_scan_time=status_data.get("last_scan_time"),
        active_positions=status_data.get("active_positions", 0),
        total_pnl=status_data.get("total_pnl", 0.0),
        realized_pnl=status_data.get("realized_pnl", 0.0),
        unrealized_pnl=status_data.get("unrealized_pnl", 0.0),
        paper_trade=status_data.get("paper_trade", True),
        data_connected=status_data.get("data_connected", False),
        risk_budget_remaining=status_data.get("risk_budget_remaining", 0.0),
        minutes_remaining=status_data.get("minutes_remaining", 0),
        recent_alerts=status_data.get("recent_alerts", []),
    )


@router.post("/start", response_model=ScanifyControlResponse)
async def start_scanner(
    current_user: User = Depends(require_tier(SubscriptionTier.PRO)),
):
    """
    Start the SCANIFY scanner system.

    Initializes data feeds, runs pre-market analysis, and begins the
    scanning loop.  Requires PRO tier or higher.
    """
    orch = _get_orchestrator()

    if orch.is_running:
        return ScanifyControlResponse(
            action="start",
            success=False,
            message="Scanner is already running.",
        )

    try:
        await orch.initialize()
        logger.info("SCANIFY scanner started by user %s", current_user.email)
        return ScanifyControlResponse(
            action="start",
            success=True,
            message="SCANIFY scanner system initialized and running.",
        )
    except Exception as exc:
        logger.exception("Failed to start scanner: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start scanner",
        ) from exc


@router.post("/stop", response_model=ScanifyControlResponse)
async def stop_scanner(
    current_user: User = Depends(require_tier(SubscriptionTier.PRO)),
):
    """
    Stop the SCANIFY scanner system.

    Gracefully shuts down scanning, closes remaining positions,
    disconnects data feeds, and persists state.  Requires PRO tier
    or higher.
    """
    orch = _get_orchestrator()

    if not orch.is_running:
        return ScanifyControlResponse(
            action="stop",
            success=False,
            message="Scanner is not running.",
        )

    try:
        await orch.shutdown()
        logger.info("SCANIFY scanner stopped by user %s", current_user.email)
        return ScanifyControlResponse(
            action="stop",
            success=True,
            message="SCANIFY scanner system stopped successfully.",
        )
    except Exception as exc:
        logger.exception("Failed to stop scanner: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to stop scanner",
        ) from exc


@router.get("/health", response_model=ScanifyHealthResponse)
async def health_check():
    """
    SCANIFY system health check.

    No authentication required.  Used for load balancers and monitoring.
    """
    if _orchestrator is None:
        return ScanifyHealthResponse(
            status="down",
            is_running=False,
            data_connected=False,
        )

    is_running = getattr(_orchestrator, "is_running", False)
    data_connected = False
    try:
        data_connected = _orchestrator.data_feed.is_connected
    except Exception:
        pass

    if is_running and data_connected:
        health_status = "healthy"
    elif is_running:
        health_status = "degraded"
    else:
        health_status = "down"

    return ScanifyHealthResponse(
        status=health_status,
        is_running=is_running,
        data_connected=data_connected,
    )


# =============================================================================
# 2. GEX DATA
# =============================================================================


@router.get("/gex/profile", response_model=GEXProfileResponse)
async def get_gex_profile(
    current_user: User = Depends(get_current_active_user),
):
    """
    Get the current GEX profile with per-strike gamma values.

    Returns the full gamma exposure landscape including all strikes,
    aggregate metrics, and key levels.  Requires authentication.
    """
    orch = _get_orchestrator()
    gex = orch.current_gex

    if gex is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No GEX profile available. Scanner may not have run yet.",
        )

    # Serialize strikes
    strike_data = []
    for s in getattr(gex, "strikes", []):
        strike_data.append(StrikeGEXResponse(
            strike=getattr(s, "strike", 0.0),
            call_gamma=getattr(s, "call_gamma", 0.0),
            put_gamma=getattr(s, "put_gamma", 0.0),
            call_oi=getattr(s, "call_oi", 0),
            put_oi=getattr(s, "put_oi", 0),
            net_gex=getattr(s, "net_gex", 0.0),
            net_charm=getattr(s, "net_charm", 0.0),
            net_vanna=getattr(s, "net_vanna", 0.0),
        ))

    return GEXProfileResponse(
        timestamp=getattr(gex, "timestamp", datetime.now(timezone.utc)),
        strikes=strike_data,
        total_net_gex=getattr(gex, "total_net_gex", 0.0),
        gamma_flip_level=getattr(gex, "gamma_flip_level", 0.0),
        call_wall=getattr(gex, "call_wall", 0.0),
        put_wall=getattr(gex, "put_wall", 0.0),
        max_pain=getattr(gex, "max_pain", 0.0),
        vol_trigger=getattr(gex, "vol_trigger", 0.0),
        gex_momentum=getattr(gex, "gex_momentum", 0.0),
        is_positive_gamma=getattr(gex, "is_positive_gamma_regime", False),
    )


@router.get("/gex/signals", response_model=List[GEXSignalResponse])
async def get_gex_signals(
    current_user: User = Depends(get_current_active_user),
):
    """
    Get active GEX-derived signals.

    Returns all GEX signals generated during the current session
    (gamma flip crossovers, wall approaches, charm-driven flows, etc.).
    Requires authentication.
    """
    orch = _get_orchestrator()

    signals = []
    for gs in getattr(orch, "gex_signals", []):
        signal_type = getattr(gs, "signal_type", "UNKNOWN")
        direction = getattr(gs, "direction", "NEUTRAL")
        signals.append(GEXSignalResponse(
            signal_type=signal_type.value if hasattr(signal_type, "value") else str(signal_type),
            direction=direction.value if hasattr(direction, "value") else str(direction),
            confidence=getattr(gs, "confidence", 0.0),
            description=getattr(gs, "description", ""),
            trigger_price=getattr(gs, "trigger_price", 0.0),
            target_price=getattr(gs, "target_price", None),
            timestamp=getattr(gs, "timestamp", datetime.now(timezone.utc)),
        ))

    return signals


@router.get("/gex/levels", response_model=GEXLevelsResponse)
async def get_gex_levels(
    current_user: User = Depends(get_current_active_user),
):
    """
    Get key GEX-derived price levels.

    Returns gamma flip, call wall, put wall, max pain, vol trigger,
    and transition zone boundaries.  Requires authentication.
    """
    orch = _get_orchestrator()
    gex = orch.current_gex

    if gex is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No GEX profile available. Scanner may not have run yet.",
        )

    return GEXLevelsResponse(
        gamma_flip=getattr(gex, "gamma_flip_level", 0.0),
        call_wall=getattr(gex, "call_wall", 0.0),
        put_wall=getattr(gex, "put_wall", 0.0),
        max_pain=getattr(gex, "max_pain", 0.0),
        plus_gex=getattr(gex, "plus_gex", 0.0),
        minus_gex=getattr(gex, "minus_gex", 0.0),
        vol_trigger=getattr(gex, "vol_trigger", 0.0),
        transition_zone_upper=getattr(gex, "transition_zone_upper", 0.0),
        transition_zone_lower=getattr(gex, "transition_zone_lower", 0.0),
        is_positive_gamma_regime=getattr(gex, "is_positive_gamma_regime", False),
    )


@router.get("/gex/history", response_model=GEXHistoryResponse)
async def get_gex_history(
    limit: int = Query(100, ge=1, le=1000, description="Max entries to return"),
    current_user: User = Depends(get_current_active_user),
):
    """
    Get GEX profile history for charting.

    Returns chronological snapshots of aggregate GEX metrics throughout
    the trading session.  Requires authentication.
    """
    orch = _get_orchestrator()

    # The orchestrator may store GEX history internally or we build
    # from the intraday data.
    gex_history = getattr(orch, "_gex_history", [])

    entries = []
    for h in gex_history[-limit:]:
        entries.append(GEXHistoryEntry(
            timestamp=h.get("timestamp", datetime.now(timezone.utc)),
            total_net_gex=h.get("total_net_gex", 0.0),
            gamma_flip_level=h.get("gamma_flip_level", 0.0),
            call_wall=h.get("call_wall", 0.0),
            put_wall=h.get("put_wall", 0.0),
        ))

    return GEXHistoryResponse(
        entries=entries,
        count=len(entries),
    )


# =============================================================================
# 3. SCANNER SIGNALS
# =============================================================================


@router.get("/signals", response_model=SignalListResponse)
async def get_all_signals(
    current_user: User = Depends(get_current_active_user),
):
    """
    Get all active scan signals (directional, premium, gamma scalp).

    Returns all signals generated during the current scanning session.
    Requires authentication.
    """
    orch = _get_orchestrator()

    serialized = [_serialize_scan_signal(s) for s in getattr(orch, "active_signals", [])]
    scan_types = list({s["scan_type"] for s in serialized})

    return SignalListResponse(
        signals=[ScanSignalResponse(**s) for s in serialized],
        total=len(serialized),
        scan_types=scan_types,
    )


@router.get("/signals/directional", response_model=SignalListResponse)
async def get_directional_signals(
    current_user: User = Depends(get_current_active_user),
):
    """
    Get directional scanner signals only.

    Filters to signals from the 5-factor directional OTM scanner.
    Requires authentication.
    """
    orch = _get_orchestrator()

    all_signals = getattr(orch, "active_signals", [])
    filtered = [
        s for s in all_signals
        if str(getattr(s, "scan_type", "")).upper() in ("DIRECTIONAL", "SCANTTYPE.DIRECTIONAL")
        or (hasattr(s, "scan_type") and hasattr(s.scan_type, "value") and s.scan_type.value == "DIRECTIONAL")
    ]

    serialized = [_serialize_scan_signal(s) for s in filtered]

    return SignalListResponse(
        signals=[ScanSignalResponse(**s) for s in serialized],
        total=len(serialized),
        scan_types=["DIRECTIONAL"] if serialized else [],
    )


@router.get("/signals/premium", response_model=SignalListResponse)
async def get_premium_signals(
    current_user: User = Depends(get_current_active_user),
):
    """
    Get premium selling scanner signals only.

    Filters to signals from the credit spread / premium selling scanner.
    Requires authentication.
    """
    orch = _get_orchestrator()

    all_signals = getattr(orch, "active_signals", [])
    filtered = [
        s for s in all_signals
        if str(getattr(s, "scan_type", "")).upper() in ("PREMIUM_SELL", "SCANTYPE.PREMIUM_SELL")
        or (hasattr(s, "scan_type") and hasattr(s.scan_type, "value") and s.scan_type.value == "PREMIUM_SELL")
    ]

    serialized = [_serialize_scan_signal(s) for s in filtered]

    return SignalListResponse(
        signals=[ScanSignalResponse(**s) for s in serialized],
        total=len(serialized),
        scan_types=["PREMIUM_SELL"] if serialized else [],
    )


@router.get("/signals/gamma", response_model=SignalListResponse)
async def get_gamma_signals(
    current_user: User = Depends(get_current_active_user),
):
    """
    Get gamma scalp scanner signals only.

    Filters to signals from the gamma scalp scanner (final 2 hours).
    Requires authentication.
    """
    orch = _get_orchestrator()

    all_signals = getattr(orch, "active_signals", [])
    filtered = [
        s for s in all_signals
        if str(getattr(s, "scan_type", "")).upper() in ("GAMMA_SCALP", "SCANTYPE.GAMMA_SCALP")
        or (hasattr(s, "scan_type") and hasattr(s.scan_type, "value") and s.scan_type.value == "GAMMA_SCALP")
    ]

    serialized = [_serialize_scan_signal(s) for s in filtered]

    return SignalListResponse(
        signals=[ScanSignalResponse(**s) for s in serialized],
        total=len(serialized),
        scan_types=["GAMMA_SCALP"] if serialized else [],
    )


@router.get("/signals/history", response_model=SignalHistoryResponse)
async def get_signal_history(
    current_user: User = Depends(get_current_active_user),
):
    """
    Get signal history for the current trading day.

    Returns all signals with aggregate breakdowns by scan type and
    direction.  Requires authentication.
    """
    orch = _get_orchestrator()

    all_signals = getattr(orch, "active_signals", [])
    serialized = [_serialize_scan_signal(s) for s in all_signals]

    # Aggregate counts
    by_type: Dict[str, int] = {}
    by_direction: Dict[str, int] = {}
    for s in serialized:
        st = s["scan_type"]
        by_type[st] = by_type.get(st, 0) + 1
        dr = s["direction"]
        by_direction[dr] = by_direction.get(dr, 0) + 1

    return SignalHistoryResponse(
        signals=[ScanSignalResponse(**s) for s in serialized],
        total=len(serialized),
        by_type=by_type,
        by_direction=by_direction,
    )


# =============================================================================
# 4. POSITIONS & TRADES
# =============================================================================


@router.get("/positions", response_model=PositionListResponse)
async def get_positions(
    current_user: User = Depends(get_current_active_user),
):
    """
    Get all active positions.

    Returns open positions with current P&L.  Requires authentication.
    """
    orch = _get_orchestrator()

    positions = [
        PositionResponse(**_serialize_position(p))
        for p in getattr(orch, "_active_positions", [])
    ]

    total_unrealized = sum(p.pnl for p in positions)

    return PositionListResponse(
        positions=positions,
        total=len(positions),
        total_unrealized_pnl=total_unrealized,
    )


@router.get("/positions/{position_id}", response_model=PositionResponse)
async def get_position_detail(
    position_id: str,
    current_user: User = Depends(get_current_active_user),
):
    """
    Get details for a single active position.

    Requires authentication.
    """
    orch = _get_orchestrator()

    for p in getattr(orch, "_active_positions", []):
        if p.get("signal_id") == position_id:
            return PositionResponse(**_serialize_position(p))

    # Also check closed positions
    for p in getattr(orch, "_closed_positions", []):
        if p.get("signal_id") == position_id:
            return PositionResponse(**_serialize_position(p))

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Position '{position_id}' not found.",
    )


@router.get("/trades", response_model=TradeLogResponse)
async def get_trades(
    current_user: User = Depends(get_current_active_user),
):
    """
    Get trade log for the current trading day.

    Returns all closed trades with P&L.  Requires authentication.
    """
    orch = _get_orchestrator()

    closed = getattr(orch, "_closed_positions", [])
    trades = [TradeLogEntry(**_serialize_trade(t)) for t in closed]

    winning = [t for t in trades if t.pnl > 0]
    losing = [t for t in trades if t.pnl <= 0]

    return TradeLogResponse(
        trades=trades,
        total=len(trades),
        winning=len(winning),
        losing=len(losing),
    )


@router.get("/trades/history", response_model=TradeLogResponse)
async def get_trade_history(
    start_date: Optional[str] = Query(
        None, description="Start date (YYYY-MM-DD)"
    ),
    end_date: Optional[str] = Query(
        None, description="End date (YYYY-MM-DD)"
    ),
    current_user: User = Depends(require_tier(SubscriptionTier.BASIC)),
):
    """
    Get historical trade log for a date range.

    Returns closed trades filtered by date.  Requires BASIC tier or
    higher.  In the current implementation, returns today's trades;
    historical persistence is handled by the trade logger.
    """
    orch = _get_orchestrator()

    # Currently returns today's closed trades.
    # In production, this would query the persistent trade log database
    # filtered by start_date and end_date.
    closed = getattr(orch, "_closed_positions", [])
    trades = [TradeLogEntry(**_serialize_trade(t)) for t in closed]

    winning = [t for t in trades if t.pnl > 0]
    losing = [t for t in trades if t.pnl <= 0]

    logger.info(
        "Trade history requested: start=%s, end=%s, user=%s",
        start_date,
        end_date,
        current_user.email,
    )

    return TradeLogResponse(
        trades=trades,
        total=len(trades),
        winning=len(winning),
        losing=len(losing),
    )


@router.get("/pnl", response_model=PnLSummaryResponse)
async def get_pnl_summary(
    current_user: User = Depends(get_current_active_user),
):
    """
    Get daily P&L summary.

    Returns total P&L, trade counts, win rate, and performance metrics.
    Requires authentication.
    """
    orch = _get_orchestrator()

    closed = getattr(orch, "_closed_positions", [])
    active = getattr(orch, "_active_positions", [])

    realized = sum(p.get("pnl", 0.0) for p in closed)
    unrealized = sum(p.get("pnl", 0.0) for p in active)
    total_pnl = realized + unrealized

    winning = [p for p in closed if p.get("pnl", 0.0) > 0]
    losing = [p for p in closed if p.get("pnl", 0.0) <= 0]

    win_rate = len(winning) / len(closed) if closed else 0.0
    avg_win = (
        sum(p["pnl"] for p in winning) / len(winning) if winning else 0.0
    )
    avg_loss = (
        sum(p["pnl"] for p in losing) / len(losing) if losing else 0.0
    )

    gross_profit = sum(p["pnl"] for p in winning) if winning else 0.0
    gross_loss = abs(sum(p["pnl"] for p in losing)) if losing else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0

    # Compute max drawdown from intraday P&L curve
    max_drawdown = 0.0
    pnl_curve = getattr(orch, "_intraday_pnl_curve", [])
    if pnl_curve:
        peak = 0.0
        for point in pnl_curve:
            pnl_val = point.get("pnl", 0.0)
            if pnl_val > peak:
                peak = pnl_val
            dd = peak - pnl_val
            if dd > max_drawdown:
                max_drawdown = dd

    today = datetime.now(timezone.utc).date().isoformat()

    return PnLSummaryResponse(
        date=today,
        total_pnl=total_pnl,
        realized_pnl=realized,
        unrealized_pnl=unrealized,
        total_trades=len(closed),
        winning_trades=len(winning),
        losing_trades=len(losing),
        win_rate=win_rate,
        avg_win=avg_win,
        avg_loss=avg_loss,
        profit_factor=profit_factor,
        max_drawdown=max_drawdown,
    )


# =============================================================================
# 5. SESSION & MARKET DATA
# =============================================================================


@router.get("/session", response_model=SessionSetupResponse)
async def get_session_setup(
    current_user: User = Depends(get_current_active_user),
):
    """
    Get session setup from pre-market analysis.

    Returns gap analysis, expected move, session classification, and
    risk assessment.  Requires authentication.
    """
    orch = _get_orchestrator()
    setup = orch.session_setup

    if setup is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session setup not available. Pre-market analysis may not have run yet.",
        )

    # Gap analysis
    gap = getattr(setup, "gap_analysis", None)
    gap_data = GapAnalysisResponse(
        gap_pct=getattr(gap, "gap_pct", 0.0) if gap else 0.0,
        gap_points=getattr(gap, "gap_points", 0.0) if gap else 0.0,
        gap_sigma=getattr(gap, "gap_sigma", 0.0) if gap else 0.0,
        classification=str(getattr(gap, "classification", "MICRO")) if gap else "MICRO",
        gap_fill_probability=getattr(gap, "gap_fill_probability", {}) if gap else {},
    )

    # Expected move
    em = getattr(setup, "expected_move", None)
    em_data = ExpectedMoveResponse(
        method1_vix1d=getattr(em, "method1_vix1d", 0.0) if em else 0.0,
        method2_straddle=getattr(em, "method2_straddle", 0.0) if em else 0.0,
        method3_rv_adjusted=getattr(em, "method3_rv_adjusted", 0.0) if em else 0.0,
        final_1sigma=getattr(em, "final_1sigma", 0.0) if em else 0.0,
        final_2sigma=getattr(em, "final_2sigma", 0.0) if em else 0.0,
        iv_rv_ratio=getattr(em, "iv_rv_ratio", 1.0) if em else 1.0,
        vol_regime=getattr(em, "vol_regime", "NORMAL") if em else "NORMAL",
    )

    session_type = getattr(setup, "session_type", "UNKNOWN")
    session_type_str = session_type.value if hasattr(session_type, "value") else str(session_type)

    return SessionSetupResponse(
        session_type=session_type_str,
        gap_analysis=gap_data,
        expected_move=em_data,
        risk_assessment=getattr(setup, "risk_assessment", ""),
        has_high_impact_events=getattr(setup, "has_high_impact_events", False),
        event_count=len(getattr(setup, "economic_events", [])),
        timestamp=getattr(setup, "timestamp", datetime.now(timezone.utc)),
    )


@router.get("/market/internals", response_model=MarketInternalsResponse)
async def get_market_internals(
    current_user: User = Depends(get_current_active_user),
):
    """
    Get current market internals snapshot.

    Returns NYSE TICK, TRIN, A/D ratio, cumulative delta, and
    extreme-condition flags.  Requires authentication.
    """
    orch = _get_orchestrator()

    # Market internals come from the data feed
    try:
        snapshot = await orch.data_feed.get_snapshot()
        internals = snapshot.get("market_internals")
    except Exception as exc:
        logger.exception("Error fetching market internals: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch market internals",
        ) from exc

    if internals is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Market internals not available.",
        )

    return MarketInternalsResponse(
        nyse_tick=getattr(internals, "nyse_tick", 0),
        nyse_tick_10min_avg=getattr(internals, "nyse_tick_10min_avg", 0.0),
        cumulative_tick=getattr(internals, "cumulative_tick", 0.0),
        nyse_trin=getattr(internals, "nyse_trin", 1.0),
        advance_decline_ratio=getattr(internals, "advance_decline_ratio", 1.0),
        up_down_volume_ratio=getattr(internals, "up_down_volume_ratio", 1.0),
        es_cumulative_delta=getattr(internals, "es_cumulative_delta", 0.0),
        tick_is_extreme_bullish=getattr(internals, "tick_is_extreme_bullish", False),
        tick_is_extreme_bearish=getattr(internals, "tick_is_extreme_bearish", False),
        trin_bullish=getattr(internals, "trin_bullish", False),
        trin_bearish=getattr(internals, "trin_bearish", False),
        timestamp=getattr(internals, "timestamp", datetime.now(timezone.utc)),
    )


@router.get("/market/expected-move", response_model=ExpectedMoveResponse)
async def get_expected_move(
    current_user: User = Depends(get_current_active_user),
):
    """
    Get expected move boundaries for the session.

    Returns 1-sigma and 2-sigma expected moves derived from VIX1D,
    ATM straddle, and realized vol.  Requires authentication.
    """
    orch = _get_orchestrator()
    setup = orch.session_setup

    if setup is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session setup not available. Pre-market analysis may not have run.",
        )

    em = getattr(setup, "expected_move", None)
    if em is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Expected move data not available.",
        )

    return ExpectedMoveResponse(
        method1_vix1d=getattr(em, "method1_vix1d", 0.0),
        method2_straddle=getattr(em, "method2_straddle", 0.0),
        method3_rv_adjusted=getattr(em, "method3_rv_adjusted", 0.0),
        final_1sigma=getattr(em, "final_1sigma", 0.0),
        final_2sigma=getattr(em, "final_2sigma", 0.0),
        iv_rv_ratio=getattr(em, "iv_rv_ratio", 1.0),
        vol_regime=getattr(em, "vol_regime", "NORMAL"),
    )


@router.get("/market/key-levels", response_model=KeyLevelsResponse)
async def get_key_levels(
    current_user: User = Depends(get_current_active_user),
):
    """
    Get key price levels for the session.

    Returns GEX-derived levels, prior-session reference prices, overnight
    range, and technical levels.  Requires authentication.
    """
    orch = _get_orchestrator()
    setup = orch.session_setup

    if setup is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session setup not available. Pre-market analysis may not have run.",
        )

    kl = getattr(setup, "key_levels", None)
    if kl is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Key levels data not available.",
        )

    return KeyLevelsResponse(
        gamma_flip=getattr(kl, "gamma_flip", 0.0),
        call_wall=getattr(kl, "call_wall", 0.0),
        put_wall=getattr(kl, "put_wall", 0.0),
        max_pain=getattr(kl, "max_pain", 0.0),
        vol_trigger=getattr(kl, "vol_trigger", 0.0),
        transition_zone_upper=getattr(kl, "transition_zone_upper", 0.0),
        transition_zone_lower=getattr(kl, "transition_zone_lower", 0.0),
        prior_high=getattr(kl, "prior_high", 0.0),
        prior_low=getattr(kl, "prior_low", 0.0),
        prior_close=getattr(kl, "prior_close", 0.0),
        overnight_high=getattr(kl, "overnight_high", 0.0),
        overnight_low=getattr(kl, "overnight_low", 0.0),
        round_levels=getattr(kl, "round_levels", []),
        moving_averages=getattr(kl, "moving_averages", {}),
    )


# =============================================================================
# 6. CALIBRATION
# =============================================================================


@router.get("/calibration/state", response_model=CalibrationStateResponse)
async def get_calibration_state(
    current_user: User = Depends(require_tier(SubscriptionTier.PRO)),
):
    """
    Get current calibration state.

    Returns factor weights, entry thresholds, regime label, and
    signal accuracy.  Requires PRO tier or higher.
    """
    orch = _get_orchestrator()
    cal_state = getattr(orch, "_calibration_state", None)

    if cal_state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Calibration state not available.",
        )

    # Extract factor weights
    weights = getattr(cal_state, "current_weights", None)
    if weights is None:
        weights_response = FactorWeightsResponse(
            market_internals=0.20,
            options_flow=0.20,
            price_action=0.20,
            gex_structure=0.20,
            cross_asset=0.20,
        )
    else:
        weights_response = FactorWeightsResponse(
            market_internals=getattr(weights, "market_internals", 0.20),
            options_flow=getattr(weights, "options_flow", 0.20),
            price_action=getattr(weights, "price_action", 0.20),
            gex_structure=getattr(weights, "gex_structure", 0.20),
            cross_asset=getattr(weights, "cross_asset", 0.20),
        )

    return CalibrationStateResponse(
        current_weights=weights_response,
        entry_threshold=getattr(cal_state, "entry_threshold", 50.0),
        stop_loss_pct=getattr(cal_state, "stop_loss_pct", 50.0),
        regime=getattr(cal_state, "regime", "NORMAL"),
        last_calibration=getattr(cal_state, "last_calibration", datetime.now(timezone.utc)),
        trade_count=getattr(cal_state, "trade_count", 0),
        gex_signal_accuracy=getattr(cal_state, "gex_signal_accuracy", 0.0),
        profit_targets_by_zone=getattr(cal_state, "profit_targets_by_zone", {}),
    )


@router.get("/calibration/scorecard", response_model=DailyScorecardResponse)
async def get_daily_scorecard(
    current_user: User = Depends(require_tier(SubscriptionTier.PRO)),
):
    """
    Get the daily performance scorecard.

    Returns win rates sliced by scan type, time zone, session type,
    and VIX regime.  Requires PRO tier or higher.
    """
    orch = _get_orchestrator()

    # Build scorecard from closed positions
    closed = getattr(orch, "_closed_positions", [])
    today = datetime.now(timezone.utc).date().isoformat()

    # Aggregate win rates by scan type
    win_rate_by_scan: Dict[str, float] = {}
    by_scan: Dict[str, List[float]] = {}
    for t in closed:
        strategy = t.get("strategy", "UNKNOWN")
        pnl = t.get("pnl", 0.0)
        if strategy not in by_scan:
            by_scan[strategy] = []
        by_scan[strategy].append(pnl)

    for st, pnls in by_scan.items():
        wins = sum(1 for p in pnls if p > 0)
        win_rate_by_scan[st] = wins / len(pnls) if pnls else 0.0

    # Average P&L by category
    avg_pnl: Dict[str, float] = {}
    for st, pnls in by_scan.items():
        avg_pnl[st] = sum(pnls) / len(pnls) if pnls else 0.0

    return DailyScorecardResponse(
        trading_date=today,
        win_rate_by_scan_type=win_rate_by_scan,
        win_rate_by_time_zone={},
        win_rate_by_session_type={},
        avg_pnl_by_category=avg_pnl,
        sharpe_ratio_by_scan={},
        max_drawdown_by_scan={},
    )


@router.post("/calibration/run", response_model=CalibrationRunResponse)
async def run_manual_calibration(
    current_user: User = Depends(require_tier(SubscriptionTier.PRO)),
):
    """
    Trigger a manual calibration run.

    Runs the daily calibrator on today's trades and updates factor
    weights and thresholds.  Requires PRO tier or higher.
    """
    orch = _get_orchestrator()

    try:
        closed = getattr(orch, "_closed_positions", [])

        if not closed:
            return CalibrationRunResponse(
                success=False,
                summary="No closed trades to calibrate against.",
                adjustments={},
            )

        # Build P&L summary for calibrator
        total_pnl = sum(p.get("pnl", 0.0) for p in closed)
        winning = [p for p in closed if p.get("pnl", 0.0) > 0]
        losing = [p for p in closed if p.get("pnl", 0.0) <= 0]
        win_rate = len(winning) / len(closed) if closed else 0.0

        pnl_summary = {
            "date": datetime.now(timezone.utc).date().isoformat(),
            "total_pnl": total_pnl,
            "total_trades": len(closed),
            "winning_trades": len(winning),
            "losing_trades": len(losing),
            "win_rate": win_rate,
        }

        result = orch.calibrator.run_daily_calibration(
            trades=closed,
            pnl_summary=pnl_summary,
            session_setup=orch.session_setup,
            calibration_state=getattr(orch, "_calibration_state", None),
        )

        # Apply updated state
        new_state = result.get("updated_state")
        if new_state is not None:
            orch._calibration_state = new_state

        # Save to disk
        orch.save_state()

        logger.info(
            "Manual calibration run by user %s: %s",
            current_user.email,
            result.get("summary", "OK"),
        )

        return CalibrationRunResponse(
            success=True,
            summary=result.get("summary", "Calibration completed successfully."),
            adjustments=result.get("adjustments", {}),
        )

    except Exception as exc:
        logger.exception("Manual calibration failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Calibration failed",
        ) from exc


@router.get("/calibration/weights", response_model=FactorWeightsResponse)
async def get_factor_weights(
    current_user: User = Depends(get_current_active_user),
):
    """
    Get current factor weights for the direction scorer.

    Returns the five-factor weight allocation used by the composite
    directional scoring engine.  Requires authentication.
    """
    orch = _get_orchestrator()
    cal_state = getattr(orch, "_calibration_state", None)

    if cal_state is None:
        # Return equal weights as default
        return FactorWeightsResponse(
            market_internals=0.20,
            options_flow=0.20,
            price_action=0.20,
            gex_structure=0.20,
            cross_asset=0.20,
        )

    weights = getattr(cal_state, "current_weights", None)
    if weights is None:
        return FactorWeightsResponse(
            market_internals=0.20,
            options_flow=0.20,
            price_action=0.20,
            gex_structure=0.20,
            cross_asset=0.20,
        )

    return FactorWeightsResponse(
        market_internals=getattr(weights, "market_internals", 0.20),
        options_flow=getattr(weights, "options_flow", 0.20),
        price_action=getattr(weights, "price_action", 0.20),
        gex_structure=getattr(weights, "gex_structure", 0.20),
        cross_asset=getattr(weights, "cross_asset", 0.20),
    )


# =============================================================================
# 7. DASHBOARD
# =============================================================================


@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(
    current_user: User = Depends(get_current_active_user),
):
    """
    Get complete dashboard data package.

    Returns a comprehensive snapshot of all SCANIFY system data for
    the frontend dashboard: SPX price, status, GEX profile, expected
    move, positions, signals, P&L curve, and session classification.
    Requires authentication.
    """
    orch = _get_orchestrator()

    try:
        dashboard_data = orch.get_dashboard_data()
    except Exception as exc:
        logger.exception("Error building dashboard data: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to build dashboard data",
        ) from exc

    # Build status sub-object
    status_data = dashboard_data.get("status", {})
    status_response = ScanifyStatusResponse(
        is_running=status_data.get("is_running", False),
        session_type=status_data.get("session_type", "UNKNOWN"),
        time_zone=status_data.get("time_zone", "UNKNOWN"),
        scan_count=status_data.get("scan_count", 0),
        last_scan_time=status_data.get("last_scan_time"),
        active_positions=status_data.get("active_positions", 0),
        total_pnl=status_data.get("total_pnl", 0.0),
        realized_pnl=status_data.get("realized_pnl", 0.0),
        unrealized_pnl=status_data.get("unrealized_pnl", 0.0),
        paper_trade=status_data.get("paper_trade", True),
        data_connected=status_data.get("data_connected", False),
        risk_budget_remaining=status_data.get("risk_budget_remaining", 0.0),
        minutes_remaining=status_data.get("minutes_remaining", 0),
        recent_alerts=status_data.get("recent_alerts", []),
    )

    return DashboardResponse(
        spx_price=dashboard_data.get("spx_price", 0.0),
        status=status_response,
        expected_move=dashboard_data.get("expected_move", {}),
        gex_profile=dashboard_data.get("gex_profile", {}),
        key_levels=dashboard_data.get("key_levels", {}),
        active_positions=dashboard_data.get("active_positions", []),
        direction_score=dashboard_data.get("direction_score", {}),
        recent_signals=dashboard_data.get("recent_signals", []),
        gex_signals=dashboard_data.get("gex_signals", []),
        intraday_pnl_curve=dashboard_data.get("intraday_pnl_curve", []),
        session_classification=dashboard_data.get("session_classification", {}),
    )


@router.get("/dashboard/gex-chart", response_model=GEXChartDataResponse)
async def get_gex_chart_data(
    current_user: User = Depends(get_current_active_user),
):
    """
    Get GEX bar chart data for the dashboard.

    Returns strike-level gamma data formatted for rendering a GEX
    bar chart with call/put gamma decomposition and key level overlays.
    Requires authentication.
    """
    orch = _get_orchestrator()
    gex = orch.current_gex

    if gex is None:
        return GEXChartDataResponse(
            strikes=[],
            net_gex_values=[],
            call_gamma_values=[],
            put_gamma_values=[],
        )

    strikes = []
    net_gex_values = []
    call_gamma_values = []
    put_gamma_values = []

    for s in getattr(gex, "strikes", []):
        strikes.append(getattr(s, "strike", 0.0))
        net_gex_values.append(getattr(s, "net_gex", 0.0))
        call_gamma_values.append(getattr(s, "call_gamma", 0.0))
        put_gamma_values.append(getattr(s, "put_gamma", 0.0))

    spx_price = 0.0
    try:
        spx_price = orch.data_feed.spx_price
    except Exception:
        pass

    return GEXChartDataResponse(
        strikes=strikes,
        net_gex_values=net_gex_values,
        call_gamma_values=call_gamma_values,
        put_gamma_values=put_gamma_values,
        gamma_flip_level=getattr(gex, "gamma_flip_level", 0.0),
        call_wall=getattr(gex, "call_wall", 0.0),
        put_wall=getattr(gex, "put_wall", 0.0),
        spx_price=spx_price,
    )


@router.get("/dashboard/direction-score", response_model=DirectionScoreBreakdownResponse)
async def get_direction_score(
    current_user: User = Depends(get_current_active_user),
):
    """
    Get direction score breakdown for the dashboard widget.

    Returns the composite directional score with individual factor
    breakdowns.  Requires authentication.
    """
    orch = _get_orchestrator()

    # Get the most recent directional signal's score
    all_signals = getattr(orch, "active_signals", [])
    dir_signals = [
        s for s in all_signals
        if hasattr(s, "scan_type")
        and (
            (hasattr(s.scan_type, "value") and s.scan_type.value == "DIRECTIONAL")
            or str(s.scan_type).upper() == "DIRECTIONAL"
        )
    ]

    if not dir_signals:
        return DirectionScoreBreakdownResponse()

    latest = dir_signals[-1]
    ds = getattr(latest, "direction_score", None)

    if ds is None:
        return DirectionScoreBreakdownResponse()

    signal = getattr(ds, "signal", "NEUTRAL")
    signal_str = signal.value if hasattr(signal, "value") else str(signal)

    return DirectionScoreBreakdownResponse(
        total_score=getattr(ds, "total_score", 0.0),
        components={
            "market_internals": getattr(ds, "market_internals_score", 0.0),
            "options_flow": getattr(ds, "options_flow_score", 0.0),
            "price_action": getattr(ds, "price_action_score", 0.0),
            "gex_structure": getattr(ds, "gex_structure_score", 0.0),
            "cross_asset": getattr(ds, "cross_asset_score", 0.0),
        },
        signal=signal_str,
        confidence=getattr(ds, "confidence", 0.0),
        factors_agreeing=getattr(ds, "factors_agreeing", 0),
    )


@router.get("/dashboard/pnl-curve", response_model=PnLCurveResponse)
async def get_pnl_curve(
    current_user: User = Depends(get_current_active_user),
):
    """
    Get intraday P&L curve for charting.

    Returns timestamped P&L points with realized/unrealized breakdown,
    plus peak and trough values.  Requires authentication.
    """
    orch = _get_orchestrator()

    pnl_curve = getattr(orch, "_intraday_pnl_curve", [])

    # Compute peak and trough
    current_pnl = 0.0
    max_pnl = 0.0
    min_pnl = 0.0

    if pnl_curve:
        pnl_values = [p.get("pnl", 0.0) for p in pnl_curve]
        current_pnl = pnl_values[-1] if pnl_values else 0.0
        max_pnl = max(pnl_values) if pnl_values else 0.0
        min_pnl = min(pnl_values) if pnl_values else 0.0

    return PnLCurveResponse(
        points=pnl_curve,
        current_pnl=current_pnl,
        max_pnl=max_pnl,
        min_pnl=min_pnl,
    )
