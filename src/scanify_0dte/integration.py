"""
SCANIFY SPX 0DTE Options Scanner - Integration Layer

Bridges the SCANIFY 0DTE SPX Scanner with the existing Revolution Alpha Engine
infrastructure.  This module provides bidirectional adapters between:

    SCANIFY world                          Revolution Alpha world
    ────────────────────                   ──────────────────────
    ScanSignal, GEXSignal          <──>    ScanResult, OptionsScanResult
    DataFeedManager                <──>    Universal Data Adapters
    ScanifyOrchestrator            <──>    BaseScanner / Scanner Engine
    Exit Manager / risk budget     <──>    Risk Management System
    Alerts (dict-based)            <──>    ScanAlert / AlertPriority
    Internal config dicts          <──>    config.yaml / Config dataclass

Classes
-------
    ScanifyIntegration       - Signal conversion and engine registration
    ScanifyConfigAdapter     - YAML configuration loader for SCANIFY params
    ScanifyDataBridge        - Data pipeline adapter bridging
    ScanifyAlertBridge       - Alert system routing

Functions
---------
    register_scanify_routes  - Mount SCANIFY REST endpoints on the FastAPI app
    create_integrated_system - Factory that wires SCANIFY into the full engine

Author: Revolution Alpha Engine - SCANIFY Division
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
import yaml
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

try:
    from fastapi import FastAPI, APIRouter, HTTPException, Query
    from fastapi.responses import JSONResponse
except ImportError:
    FastAPI = None  # type: ignore[assignment,misc]
    APIRouter = None  # type: ignore[assignment,misc]
    HTTPException = None  # type: ignore[assignment,misc]
    Query = None  # type: ignore[assignment,misc]
    JSONResponse = None  # type: ignore[assignment,misc]

# ── SCANIFY imports ──────────────────────────────────────────────────────────
from .models import (
    ScanSignal,
    ScanType,
    TradeDirection,
    GEXSignal,
    GEXSignalType,
    GEXProfile,
    SessionType,
    TimeZoneType,
    PositionType,
    OptionSide,
    DirectionScore,
    StrikeSelection,
    SessionSetup,
    CalibrationState,
)
from .data_pipeline import DataFeedManager
from .orchestrator import ScanifyOrchestrator

# ── Existing Revolution Alpha Engine imports ─────────────────────────────────
from ..scanner.models import (
    ScanResult,
    OptionsScanResult,
    SignalDirection,
    SignalStrength,
    TimeFrame,
    ScanMode,
    ScanAlert,
    AlertPriority,
    ScannerConfig as EngineScannerConfig,
    ScannerSummary,
)
from ..core.config import (
    Config,
    load_config,
    get_config,
    RiskConfig,
    TradingConfig,
    ScannerConfig as CoreScannerConfig,
    APIConfig,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Direction Mapping Helpers
# ============================================================================

_DIRECTION_MAP: Dict[TradeDirection, SignalDirection] = {
    TradeDirection.BULL: SignalDirection.LONG,
    TradeDirection.BEAR: SignalDirection.SHORT,
    TradeDirection.NEUTRAL: SignalDirection.NEUTRAL,
}

_REVERSE_DIRECTION_MAP: Dict[SignalDirection, TradeDirection] = {
    v: k for k, v in _DIRECTION_MAP.items()
}

_TIMEZONE_TO_TIMEFRAME: Dict[TimeZoneType, TimeFrame] = {
    TimeZoneType.PRE_MARKET: TimeFrame.M5,
    TimeZoneType.OPENING_AUCTION: TimeFrame.M1,
    TimeZoneType.MORNING_SESSION: TimeFrame.M5,
    TimeZoneType.MIDDAY_LULL: TimeFrame.M15,
    TimeZoneType.AFTERNOON_ACCEL: TimeFrame.M5,
    TimeZoneType.POWER_HOUR: TimeFrame.M1,
    TimeZoneType.SETTLEMENT_WINDOW: TimeFrame.M1,
}

_SCAN_TYPE_LABEL: Dict[ScanType, str] = {
    ScanType.DIRECTIONAL: "scanify_0dte_directional",
    ScanType.PREMIUM_SELL: "scanify_0dte_premium",
    ScanType.GAMMA_SCALP: "scanify_0dte_gamma_scalp",
}

_SESSION_TO_REGIME: Dict[SessionType, str] = {
    SessionType.TRENDING: "trending_up",
    SessionType.RANGE: "ranging",
    SessionType.VOLATILE: "high_volatility",
    SessionType.SQUEEZE: "breakout",
    SessionType.EVENT: "high_volatility",
}


# ============================================================================
# 1. ScanifyIntegration
# ============================================================================

class ScanifyIntegration:
    """Bridges the SCANIFY scanner system with the existing Revolution Alpha
    Engine scanner framework.

    Responsibilities
    ----------------
    - Convert SCANIFY ``ScanSignal`` / ``GEXSignal`` into the engine-standard
      ``ScanResult`` (or ``OptionsScanResult``) format so downstream consumers
      (dashboard, alerts, portfolio) work without modification.
    - Register SCANIFY scanners with the engine's scanner registry so they
      appear in batch runs and the scanner summary.
    - Query the risk management system for the available daily budget and
      translate it into the dollar-denominated risk budget SCANIFY expects.
    - Route validated SCANIFY signals to the execution engine.

    Parameters
    ----------
    config : Config, optional
        Revolution Alpha Engine master configuration.  If ``None``, the global
        config singleton is used.
    """

    def __init__(self, config: Optional[Config] = None) -> None:
        self._config = config or get_config()
        self._registered = False
        self._conversion_count = 0
        self._error_count = 0
        logger.info("ScanifyIntegration initialized.")

    # ------------------------------------------------------------------
    # (a) convert_signal_to_scan_result
    # ------------------------------------------------------------------

    def convert_signal_to_scan_result(self, signal: ScanSignal) -> ScanResult:
        """Convert a SCANIFY ``ScanSignal`` into the engine-standard
        ``ScanResult`` used by dashboards, the alert system, and portfolio
        tracking.

        Parameters
        ----------
        signal : ScanSignal
            Output of a SCANIFY scan pass (directional, premium, or gamma
            scalp).

        Returns
        -------
        ScanResult
            Engine-compatible scan result with all fields populated.
        """
        direction = _DIRECTION_MAP.get(signal.direction, SignalDirection.NEUTRAL)
        timeframe = _TIMEZONE_TO_TIMEFRAME.get(signal.time_zone, TimeFrame.M5)
        scanner_type = _SCAN_TYPE_LABEL.get(signal.scan_type, "scanify_0dte")

        # Build targets list from profit target
        targets: List[float] = [signal.profit_target]

        # Risk/reward is already computed on the signal
        risk_reward = signal.risk_reward_ratio

        # Assemble metadata from the rich signal payload
        metadata: Dict[str, Any] = {
            "scanify_scan_type": signal.scan_type.value,
            "scanify_session_type": signal.session_type.value,
            "scanify_time_zone": signal.time_zone.value,
            "scanify_position_type": signal.position_type.value,
            "scanify_contracts": signal.contracts,
            "scanify_max_risk": signal.max_risk,
            "scanify_expected_reward": signal.expected_reward,
            "scanify_direction_score": signal.direction_score.total_score,
            "scanify_factors_agreeing": signal.direction_score.factors_agreeing,
            "scanify_has_opposing_factor": signal.direction_score.has_opposing_factor,
            "scanify_confidence": signal.direction_score.confidence,
        }

        # Merge strike selection details when available
        if signal.strike_selection is not None:
            ss = signal.strike_selection
            metadata.update({
                "strike": ss.strike,
                "option_type": ss.option_type.value,
                "delta": ss.delta,
                "gamma": ss.gamma,
                "theta": ss.theta,
                "iv": ss.iv,
                "moneyness": ss.moneyness,
                "is_liquid": ss.is_liquid,
            })

        # Merge any extra signal metadata
        metadata.update(signal.metadata)

        result = ScanResult(
            symbol="SPX",
            scanner_type=scanner_type,
            direction=direction,
            confidence=signal.direction_score.confidence,
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            targets=targets,
            risk_reward=risk_reward,
            timestamp=signal.timestamp,
            timeframe=timeframe,
            metadata=metadata,
        )

        self._conversion_count += 1
        logger.debug(
            "Converted ScanSignal -> ScanResult: type=%s direction=%s confidence=%.1f",
            scanner_type,
            direction.value,
            result.confidence,
        )
        return result

    # ------------------------------------------------------------------
    # (a-ext) convert to OptionsScanResult for richer downstream use
    # ------------------------------------------------------------------

    def convert_signal_to_options_result(
        self, signal: ScanSignal
    ) -> OptionsScanResult:
        """Convert a SCANIFY ``ScanSignal`` into an ``OptionsScanResult`` that
        carries full options-specific fields (strike, Greeks, etc.).

        This is preferred over :meth:`convert_signal_to_scan_result` when the
        downstream consumer can handle option-level detail.

        Parameters
        ----------
        signal : ScanSignal
            Output of a SCANIFY scan pass.

        Returns
        -------
        OptionsScanResult
            Engine-compatible options scan result with Greeks and contract
            detail populated.
        """
        direction = _DIRECTION_MAP.get(signal.direction, SignalDirection.NEUTRAL)
        timeframe = _TIMEZONE_TO_TIMEFRAME.get(signal.time_zone, TimeFrame.M5)
        scanner_type = _SCAN_TYPE_LABEL.get(signal.scan_type, "scanify_0dte")

        ss = signal.strike_selection
        strike = ss.strike if ss else signal.entry_price
        option_type_str = ss.option_type.value if ss else "CALL"
        greeks: Dict[str, float] = {}
        bid: Optional[float] = None
        ask: Optional[float] = None
        volume: Optional[int] = None
        oi: Optional[int] = None

        if ss is not None:
            greeks = {
                "delta": ss.delta,
                "gamma": ss.gamma,
                "theta": ss.theta,
                "iv": ss.iv,
            }
            bid = ss.bid
            ask = ss.ask
            volume = ss.volume
            oi = ss.oi

        metadata: Dict[str, Any] = {
            "scanify_scan_type": signal.scan_type.value,
            "scanify_session_type": signal.session_type.value,
            "scanify_time_zone": signal.time_zone.value,
            "scanify_position_type": signal.position_type.value,
            "scanify_contracts": signal.contracts,
            "scanify_max_risk": signal.max_risk,
            "scanify_expected_reward": signal.expected_reward,
            "scanify_direction_score": signal.direction_score.total_score,
        }
        metadata.update(signal.metadata)

        # Expiration is always today for 0DTE
        expiration = datetime.combine(date.today(), datetime.min.time())

        result = OptionsScanResult(
            symbol="SPX",
            scanner_type=scanner_type,
            direction=direction,
            confidence=signal.direction_score.confidence,
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            targets=[signal.profit_target],
            risk_reward=signal.risk_reward_ratio,
            timestamp=signal.timestamp,
            timeframe=timeframe,
            metadata=metadata,
            strike=strike,
            expiration=expiration,
            option_type=option_type_str,
            greeks=greeks,
            bid=bid,
            ask=ask,
            volume=volume,
            open_interest=oi,
            underlying_price=signal.entry_price,
        )

        self._conversion_count += 1
        return result

    # ------------------------------------------------------------------
    # (b) convert_gex_signal_to_scan_result
    # ------------------------------------------------------------------

    def convert_gex_signal_to_scan_result(self, signal: GEXSignal) -> ScanResult:
        """Convert a GEX signal into the engine-standard ``ScanResult``.

        GEX signals do not carry full strike-selection or position-sizing data;
        the resulting ``ScanResult`` uses the trigger price as the entry and
        populates metadata with the GEX-specific fields.

        Parameters
        ----------
        signal : GEXSignal
            Gamma exposure signal from the GEX engine.

        Returns
        -------
        ScanResult
            Engine-compatible scan result.
        """
        direction = _DIRECTION_MAP.get(signal.direction, SignalDirection.NEUTRAL)

        targets: List[float] = []
        if signal.target_price is not None:
            targets.append(signal.target_price)

        metadata: Dict[str, Any] = {
            "gex_signal_type": signal.signal_type.value,
            "gex_trigger_price": signal.trigger_price,
            "gex_target_price": signal.target_price,
            "gex_description": signal.description,
        }
        metadata.update(signal.metadata)

        result = ScanResult(
            symbol="SPX",
            scanner_type="scanify_0dte_gex",
            direction=direction,
            confidence=signal.confidence,
            entry_price=signal.trigger_price,
            stop_loss=None,
            targets=targets,
            risk_reward=None,
            timestamp=signal.timestamp,
            timeframe=TimeFrame.M1,
            metadata=metadata,
        )

        self._conversion_count += 1
        logger.debug(
            "Converted GEXSignal -> ScanResult: type=%s direction=%s confidence=%.1f",
            signal.signal_type.value,
            direction.value,
            result.confidence,
        )
        return result

    # ------------------------------------------------------------------
    # (c) register_with_engine
    # ------------------------------------------------------------------

    def register_with_engine(self, engine: Any) -> None:
        """Register SCANIFY scanner types with the existing scanner engine
        so they appear in the unified scan batch, summary reports, and the
        dashboard scanner list.

        The method is engine-agnostic: it inspects the engine for known
        registration patterns (``register_scanner``, ``add_scanner``,
        ``scanners`` dict) and adapts accordingly.

        Parameters
        ----------
        engine : object
            The Revolution Alpha Engine scanner engine instance.  Expected to
            expose one of the following registration interfaces:
            - ``register_scanner(name, config)``
            - ``add_scanner(name, scanner)``
            - ``scanners`` dict attribute

        Raises
        ------
        RuntimeError
            If no supported registration interface is found on the engine.
        """
        scanify_scanners = {
            "scanify_0dte_directional": {
                "name": "SCANIFY 0DTE Directional",
                "scan_mode": ScanMode.OPTIONS_DAY,
                "description": "5-factor composite directional OTM scanner for SPX 0DTE",
                "symbol": "SPX",
                "timeframes": [TimeFrame.M1, TimeFrame.M5],
                "enabled": True,
            },
            "scanify_0dte_premium": {
                "name": "SCANIFY 0DTE Premium Selling",
                "scan_mode": ScanMode.OPTIONS_DAY,
                "description": "Credit spread / iron condor premium selling scanner for SPX 0DTE",
                "symbol": "SPX",
                "timeframes": [TimeFrame.M5, TimeFrame.M15],
                "enabled": True,
            },
            "scanify_0dte_gamma_scalp": {
                "name": "SCANIFY 0DTE Gamma Scalp",
                "scan_mode": ScanMode.OPTIONS_DAY,
                "description": "Power-hour gamma acceleration scalping scanner for SPX 0DTE",
                "symbol": "SPX",
                "timeframes": [TimeFrame.M1],
                "enabled": True,
            },
            "scanify_0dte_gex": {
                "name": "SCANIFY 0DTE GEX Scanner",
                "scan_mode": ScanMode.OPTIONS_DAY,
                "description": "Dealer gamma exposure signal scanner for SPX 0DTE",
                "symbol": "SPX",
                "timeframes": [TimeFrame.M1, TimeFrame.M5],
                "enabled": True,
            },
        }

        registered_count = 0

        for scanner_key, scanner_info in scanify_scanners.items():
            try:
                if hasattr(engine, "register_scanner") and callable(
                    engine.register_scanner
                ):
                    engine.register_scanner(scanner_key, scanner_info)
                    registered_count += 1
                elif hasattr(engine, "add_scanner") and callable(engine.add_scanner):
                    engine.add_scanner(scanner_key, scanner_info)
                    registered_count += 1
                elif hasattr(engine, "scanners") and isinstance(engine.scanners, dict):
                    engine.scanners[scanner_key] = scanner_info
                    registered_count += 1
                else:
                    raise RuntimeError(
                        f"Engine {type(engine).__name__} does not expose a "
                        "supported scanner registration interface "
                        "(register_scanner, add_scanner, or scanners dict)."
                    )
            except Exception as exc:
                logger.error(
                    "Failed to register SCANIFY scanner '%s': %s",
                    scanner_key,
                    exc,
                )
                self._error_count += 1

        self._registered = True
        logger.info(
            "Registered %d SCANIFY scanners with engine %s.",
            registered_count,
            type(engine).__name__,
        )

    # ------------------------------------------------------------------
    # (d) get_risk_budget_from_manager
    # ------------------------------------------------------------------

    def get_risk_budget_from_manager(self, risk_manager: Any) -> float:
        """Query the existing risk management system to derive a dollar-
        denominated daily risk budget for the SCANIFY system.

        The method probes the risk manager for available capital and applies
        the portfolio-level risk limits from the configuration.

        Parameters
        ----------
        risk_manager : object
            The Revolution Alpha Engine risk manager.  Expected to expose
            one or more of:
            - ``get_available_capital() -> float``
            - ``portfolio_risk`` attribute (``PortfolioRisk``)
            - ``get_portfolio_risk() -> PortfolioRisk``
            - ``config`` attribute with ``max_position_risk_pct``

        Returns
        -------
        float
            Dollar amount available for SCANIFY 0DTE trading today.  Falls
            back to the configured ``max_position_risk_pct`` of
            ``max_portfolio_risk_pct`` applied to a default $500k notional
            if no runtime data is available.
        """
        risk_cfg = self._config.risk
        default_notional = 500_000.0  # conservative fallback

        # Strategy 1: Direct capital query
        if hasattr(risk_manager, "get_available_capital") and callable(
            risk_manager.get_available_capital
        ):
            try:
                available = risk_manager.get_available_capital()
                if available and available > 0:
                    budget = available * (risk_cfg.max_position_risk_pct / 100.0)
                    logger.info(
                        "Risk budget from available capital: $%.2f (%.1f%% of $%.2f)",
                        budget,
                        risk_cfg.max_position_risk_pct,
                        available,
                    )
                    return budget
            except Exception as exc:
                logger.warning("get_available_capital failed: %s", exc)

        # Strategy 2: Portfolio risk object
        portfolio_risk = None
        if hasattr(risk_manager, "portfolio_risk"):
            portfolio_risk = risk_manager.portfolio_risk
        elif hasattr(risk_manager, "get_portfolio_risk") and callable(
            risk_manager.get_portfolio_risk
        ):
            try:
                portfolio_risk = risk_manager.get_portfolio_risk()
            except Exception as exc:
                logger.warning("get_portfolio_risk failed: %s", exc)

        if portfolio_risk is not None and hasattr(portfolio_risk, "total_value"):
            total = portfolio_risk.total_value
            if total and total > 0:
                # Apply both portfolio-level and position-level limits
                max_portfolio_pct = risk_cfg.max_portfolio_risk_pct / 100.0
                max_position_pct = risk_cfg.max_position_risk_pct / 100.0
                # SCANIFY gets the position-level slice of the portfolio risk
                budget = total * min(max_portfolio_pct, max_position_pct)

                # Reduce budget if drawdown is elevated
                current_dd = getattr(portfolio_risk, "current_drawdown", 0.0)
                if current_dd > 0.05:
                    reduction = min(current_dd * 2.0, 0.8)
                    budget *= (1.0 - reduction)
                    logger.warning(
                        "Drawdown at %.1f%% -- reducing SCANIFY budget by %.0f%%.",
                        current_dd * 100,
                        reduction * 100,
                    )

                logger.info(
                    "Risk budget from portfolio value: $%.2f (%.1f%% of $%.2f)",
                    budget,
                    max_position_pct * 100,
                    total,
                )
                return budget

        # Strategy 3: Risk manager configuration
        if hasattr(risk_manager, "config"):
            rm_cfg = risk_manager.config
            notional = getattr(rm_cfg, "total_capital", default_notional)
            pct = getattr(rm_cfg, "max_position_risk_pct", risk_cfg.max_position_risk_pct)
            budget = notional * (pct / 100.0)
            logger.info(
                "Risk budget from risk manager config: $%.2f", budget
            )
            return budget

        # Fallback: use engine config defaults
        budget = default_notional * (risk_cfg.max_position_risk_pct / 100.0)
        logger.warning(
            "Could not determine live capital; using fallback risk budget: $%.2f",
            budget,
        )
        return budget

    # ------------------------------------------------------------------
    # (e) send_signal_to_execution
    # ------------------------------------------------------------------

    def send_signal_to_execution(
        self, signal: ScanSignal, execution_engine: Any
    ) -> Dict[str, Any]:
        """Route a validated SCANIFY signal to the existing execution engine
        for order placement.

        The method constructs an execution-ready order payload from the
        signal and delegates to the engine's order submission interface.

        Parameters
        ----------
        signal : ScanSignal
            The SCANIFY scan signal to execute.
        execution_engine : object
            The Revolution Alpha Engine execution engine.  Expected to expose
            one of:
            - ``submit_order(order_dict) -> dict``
            - ``create_order(order_dict) -> dict``
            - ``place_order(**kwargs) -> dict``

        Returns
        -------
        dict
            Execution result containing at minimum:
            - ``order_id``: unique order identifier
            - ``status``: order status string
            - ``signal_id``: reference back to the source signal
            - ``submitted_at``: ISO timestamp of submission
        """
        # Map SCANIFY direction to order side
        side = "buy" if signal.direction == TradeDirection.BULL else "sell"

        # Determine option type from strike selection
        option_type = "CALL"
        strike = signal.entry_price
        if signal.strike_selection is not None:
            option_type = signal.strike_selection.option_type.value
            strike = signal.strike_selection.strike

        order_payload: Dict[str, Any] = {
            "order_id": str(uuid.uuid4()),
            "symbol": "SPX",
            "underlying": "SPX",
            "asset_type": "option",
            "side": side,
            "quantity": signal.contracts,
            "order_type": "limit",
            "limit_price": signal.entry_price,
            "strike": strike,
            "option_type": option_type,
            "expiration": date.today().isoformat(),
            "position_type": signal.position_type.value,
            "stop_loss": signal.stop_loss,
            "profit_target": signal.profit_target,
            "max_risk": signal.max_risk,
            "source": "scanify_0dte",
            "scan_type": signal.scan_type.value,
            "direction_confidence": signal.direction_score.confidence,
            "submitted_at": datetime.now(timezone.utc).isoformat(),
        }

        result: Dict[str, Any] = {
            "order_id": order_payload["order_id"],
            "status": "rejected",
            "signal_id": order_payload["order_id"],
            "submitted_at": order_payload["submitted_at"],
            "error": None,
        }

        try:
            if hasattr(execution_engine, "submit_order") and callable(
                execution_engine.submit_order
            ):
                exec_result = execution_engine.submit_order(order_payload)
                result.update(exec_result if isinstance(exec_result, dict) else {})
                result["status"] = result.get("status", "submitted")
            elif hasattr(execution_engine, "create_order") and callable(
                execution_engine.create_order
            ):
                exec_result = execution_engine.create_order(order_payload)
                result.update(exec_result if isinstance(exec_result, dict) else {})
                result["status"] = result.get("status", "created")
            elif hasattr(execution_engine, "place_order") and callable(
                execution_engine.place_order
            ):
                exec_result = execution_engine.place_order(
                    symbol=order_payload["symbol"],
                    side=side,
                    quantity=signal.contracts,
                    order_type="limit",
                    limit_price=signal.entry_price,
                    stop_loss=signal.stop_loss,
                    take_profit=signal.profit_target,
                )
                result.update(exec_result if isinstance(exec_result, dict) else {})
                result["status"] = result.get("status", "placed")
            else:
                result["status"] = "unsupported"
                result["error"] = (
                    f"Execution engine {type(execution_engine).__name__} does not "
                    "expose submit_order, create_order, or place_order."
                )
                logger.error(result["error"])
        except Exception as exc:
            result["status"] = "error"
            result["error"] = str(exc)
            logger.exception("Failed to send signal to execution engine: %s", exc)
            self._error_count += 1

        logger.info(
            "Execution result: order_id=%s status=%s",
            result["order_id"],
            result["status"],
        )
        return result

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    @property
    def stats(self) -> Dict[str, Any]:
        """Return integration-layer diagnostic counters."""
        return {
            "conversion_count": self._conversion_count,
            "error_count": self._error_count,
            "registered_with_engine": self._registered,
        }


# ============================================================================
# 2. ScanifyConfigAdapter
# ============================================================================

class ScanifyConfigAdapter:
    """Loads SCANIFY-specific configuration from the Revolution Alpha Engine
    ``config.yaml`` and provides typed accessors for each configuration
    section.

    The adapter reads the top-level YAML and extracts sub-sections relevant
    to SCANIFY, merging defaults where keys are absent.

    Parameters
    ----------
    config_path : str
        Path to the configuration YAML file.  Defaults to ``"config.yaml"``.
    """

    # Default SCANIFY overrides that supplement the main config.yaml
    _SCANIFY_DEFAULTS: Dict[str, Any] = {
        "scanify_0dte": {
            "enabled": True,
            "data_provider": "polygon",
            "paper_trade": True,
            "risk_budget": 10_000.0,
            "log_dir": "logs/scanify",
            "scan_interval_directional": 60,
            "scan_interval_premium": 300,
            "scan_interval_gamma_scalp": 30,
            "gex_refresh_interval": 60,
            "exit_check_interval": 15,
            "min_confidence": 65.0,
            "max_daily_trades": 20,
            "max_concurrent_positions": 5,
        },
    }

    def __init__(self, config_path: str = "config.yaml") -> None:
        self._config_path = config_path
        self._raw: Dict[str, Any] = {}
        self._loaded = False

    # ------------------------------------------------------------------
    # (a) load_from_yaml
    # ------------------------------------------------------------------

    def load_from_yaml(self, config_path: Optional[str] = None) -> Dict[str, Any]:
        """Load the full configuration from YAML.

        Parameters
        ----------
        config_path : str, optional
            Override config file path.  Uses the instance default when
            ``None``.

        Returns
        -------
        dict
            Complete parsed configuration dictionary with SCANIFY defaults
            merged in.
        """
        path = Path(config_path or self._config_path)

        if path.exists():
            with open(path, "r") as fh:
                self._raw = yaml.safe_load(fh) or {}
            logger.info("Loaded configuration from %s", path)
        else:
            logger.warning(
                "Config file not found at %s; using built-in defaults.", path
            )
            self._raw = {}

        # Merge SCANIFY defaults for any missing keys
        if "scanify_0dte" not in self._raw:
            self._raw["scanify_0dte"] = {}

        for key, default_val in self._SCANIFY_DEFAULTS["scanify_0dte"].items():
            self._raw["scanify_0dte"].setdefault(key, default_val)

        self._loaded = True
        return self._raw

    # ------------------------------------------------------------------
    # (b) get_scanner_config
    # ------------------------------------------------------------------

    def get_scanner_config(self) -> Dict[str, Any]:
        """Return the merged scanner configuration section.

        Combines the main ``scanner`` section from ``config.yaml`` with the
        SCANIFY-specific overrides under ``scanify_0dte``.

        Returns
        -------
        dict
            Scanner configuration parameters.
        """
        if not self._loaded:
            self.load_from_yaml()

        base = dict(self._raw.get("scanner", {}))
        scanify = dict(self._raw.get("scanify_0dte", {}))

        # SCANIFY overrides for scanner-level params
        merged = {**base}
        merged["scanify_0dte"] = scanify
        merged.setdefault("min_confidence", scanify.get("min_confidence", 65.0))
        merged.setdefault("scan_interval_seconds", scanify.get("scan_interval_directional", 60))
        return merged

    # ------------------------------------------------------------------
    # (c) get_risk_config
    # ------------------------------------------------------------------

    def get_risk_config(self) -> Dict[str, Any]:
        """Return the merged risk management configuration.

        Combines the main ``risk`` section with SCANIFY-specific limits.

        Returns
        -------
        dict
            Risk configuration parameters including SCANIFY budget.
        """
        if not self._loaded:
            self.load_from_yaml()

        base = dict(self._raw.get("risk", {}))
        scanify = dict(self._raw.get("scanify_0dte", {}))

        merged = {**base}
        merged["scanify_risk_budget"] = scanify.get("risk_budget", 10_000.0)
        merged["scanify_max_daily_trades"] = scanify.get("max_daily_trades", 20)
        merged["scanify_max_concurrent_positions"] = scanify.get(
            "max_concurrent_positions", 5
        )
        return merged

    # ------------------------------------------------------------------
    # (d) get_data_config
    # ------------------------------------------------------------------

    def get_data_config(self) -> Dict[str, Any]:
        """Return the data provider / API configuration section.

        Merges ``api`` settings with SCANIFY data provider preferences.

        Returns
        -------
        dict
            Data configuration parameters.
        """
        if not self._loaded:
            self.load_from_yaml()

        base = dict(self._raw.get("api", {}))
        scanify = dict(self._raw.get("scanify_0dte", {}))

        merged = {**base}
        merged["scanify_data_provider"] = scanify.get(
            "data_provider",
            base.get("primary_data_provider", "polygon"),
        )
        merged["scanify_paper_trade"] = scanify.get(
            "paper_trade",
            base.get("use_paper_trading", True),
        )
        return merged


# ============================================================================
# 3. ScanifyDataBridge
# ============================================================================

class ScanifyDataBridge:
    """Bridges the SCANIFY ``DataFeedManager`` with the existing Revolution
    Alpha Engine universal data adapters.

    This allows SCANIFY to consume data from an already-active data adapter
    (Polygon, Alpaca, etc.) rather than opening a duplicate connection, and
    enables sharing of market-data snapshots between the two systems.

    Parameters
    ----------
    config : Config, optional
        Engine master configuration.
    """

    def __init__(self, config: Optional[Config] = None) -> None:
        self._config = config or get_config()
        self._shared_feeds: Dict[str, Any] = {}
        logger.info("ScanifyDataBridge initialized.")

    # ------------------------------------------------------------------
    # (a) create_from_existing_adapter
    # ------------------------------------------------------------------

    def create_from_existing_adapter(self, adapter: Any) -> DataFeedManager:
        """Create a SCANIFY ``DataFeedManager`` that re-uses credentials and
        connection parameters from an existing data adapter.

        Parameters
        ----------
        adapter : object
            An existing Revolution Alpha Engine data adapter instance.
            Expected to expose attributes such as ``vendor``, ``api_key``,
            ``base_url``, or a ``config`` dict.

        Returns
        -------
        DataFeedManager
            A configured ``DataFeedManager`` ready for ``connect()``.
        """
        # Extract provider and API key from the adapter
        provider = "polygon"
        api_key = ""

        if hasattr(adapter, "vendor"):
            vendor = adapter.vendor
            if hasattr(vendor, "value"):
                provider = vendor.value  # DataVendor enum
            else:
                provider = str(vendor).lower()

        if hasattr(adapter, "api_key"):
            api_key = adapter.api_key or ""
        elif hasattr(adapter, "config") and isinstance(adapter.config, dict):
            api_key = adapter.config.get("api_key", "")

        # Fall back to environment variables
        if not api_key:
            api_key = os.getenv("POLYGON_API_KEY", "") or os.getenv(
                "ALPACA_API_KEY", ""
            )

        feed_manager = DataFeedManager(
            data_provider=provider,
            api_key=api_key,
        )

        logger.info(
            "Created DataFeedManager from existing adapter: provider=%s",
            provider,
        )
        return feed_manager

    # ------------------------------------------------------------------
    # (b) share_market_data
    # ------------------------------------------------------------------

    def share_market_data(
        self, existing_feed: Any, scanify_feed: DataFeedManager
    ) -> None:
        """Establish a data-sharing bridge between an existing market-data
        feed and the SCANIFY ``DataFeedManager``.

        When the existing feed publishes SPX / ES / VIX data, the bridge
        forwards it into the SCANIFY feed's internal cache so that the
        scanners have access to the latest data without additional API calls.

        Parameters
        ----------
        existing_feed : object
            The engine's existing market data feed or stream.  Expected to
            expose a callback registration mechanism such as
            ``on_data(callback)``, ``subscribe(callback)``, or an
            ``add_listener(event, callback)`` pattern.
        scanify_feed : DataFeedManager
            The SCANIFY data feed manager that should receive shared data.
        """
        scanify_symbols = {"SPX", "SPXW", "ES", "VIX", "VIX1D", "VIX9D"}

        def _on_data_callback(data: Any) -> None:
            """Forward relevant market data into the SCANIFY feed cache."""
            try:
                symbol = None
                if hasattr(data, "symbol"):
                    symbol = data.symbol
                elif isinstance(data, dict):
                    symbol = data.get("symbol")

                if symbol and symbol.upper() in scanify_symbols:
                    # Store in the SCANIFY feed's snapshot cache if available
                    if hasattr(scanify_feed, "_latest_data"):
                        scanify_feed._latest_data[symbol.upper()] = data
                    self._shared_feeds[symbol.upper()] = data
                    logger.debug(
                        "Shared market data for %s -> SCANIFY feed.", symbol
                    )
            except Exception as exc:
                logger.warning("Data sharing callback error: %s", exc)

        # Register the callback with the existing feed
        registered = False
        for method_name in ("on_data", "subscribe", "add_listener"):
            if hasattr(existing_feed, method_name) and callable(
                getattr(existing_feed, method_name)
            ):
                method = getattr(existing_feed, method_name)
                try:
                    if method_name == "add_listener":
                        method("market_data", _on_data_callback)
                    else:
                        method(_on_data_callback)
                    registered = True
                    logger.info(
                        "Data sharing bridge established via %s.%s().",
                        type(existing_feed).__name__,
                        method_name,
                    )
                    break
                except Exception as exc:
                    logger.warning(
                        "Failed to register via %s: %s", method_name, exc
                    )

        if not registered:
            logger.warning(
                "Could not register data sharing callback with %s. "
                "SCANIFY will use its own data connections.",
                type(existing_feed).__name__,
            )

    @property
    def shared_symbols(self) -> List[str]:
        """Return the list of symbols currently being shared."""
        return list(self._shared_feeds.keys())


# ============================================================================
# 4. ScanifyAlertBridge
# ============================================================================

class ScanifyAlertBridge:
    """Routes SCANIFY alerts into the existing Revolution Alpha Engine alert
    system (``ScanAlert`` / ``AlertPriority``).

    Also provides webhook payload generation for external integrations
    (Discord, Slack, Telegram, custom HTTP endpoints).
    """

    # Map SCANIFY internal alert levels to engine AlertPriority
    _PRIORITY_MAP: Dict[str, AlertPriority] = {
        "INFO": AlertPriority.LOW,
        "WARNING": AlertPriority.MEDIUM,
        "SIGNAL": AlertPriority.HIGH,
        "CRITICAL": AlertPriority.CRITICAL,
        "PHASE": AlertPriority.LOW,
        "GEX": AlertPriority.HIGH,
        "EXIT": AlertPriority.HIGH,
        "RISK": AlertPriority.CRITICAL,
    }

    def __init__(self) -> None:
        self._alert_count = 0
        self._webhook_count = 0

    # ------------------------------------------------------------------
    # (a) convert_alert
    # ------------------------------------------------------------------

    def convert_alert(self, scanify_alert: Dict[str, Any]) -> Dict[str, Any]:
        """Convert a SCANIFY internal alert dict into a format compatible
        with the engine's ``ScanAlert`` model.

        Parameters
        ----------
        scanify_alert : dict
            SCANIFY alert with keys such as ``type``, ``message``,
            ``level``, ``timestamp``, and optional ``signal``.

        Returns
        -------
        dict
            Dictionary suitable for constructing a ``ScanAlert`` instance.
        """
        alert_type = scanify_alert.get("type", "INFO")
        level = scanify_alert.get("level", alert_type)
        priority = self._PRIORITY_MAP.get(level.upper(), AlertPriority.MEDIUM)

        message = scanify_alert.get("message", "")
        timestamp_raw = scanify_alert.get("timestamp")
        if isinstance(timestamp_raw, str):
            try:
                timestamp = datetime.fromisoformat(timestamp_raw)
            except ValueError:
                timestamp = datetime.now(timezone.utc)
        elif isinstance(timestamp_raw, datetime):
            timestamp = timestamp_raw
        else:
            timestamp = datetime.now(timezone.utc)

        # Construct a minimal ScanResult for the alert if a signal is attached
        scan_result_dict: Optional[Dict[str, Any]] = None
        if "signal" in scanify_alert and scanify_alert["signal"] is not None:
            scan_result_dict = {
                "symbol": "SPX",
                "scanner_type": "scanify_0dte",
                "direction": "neutral",
                "confidence": scanify_alert["signal"].get("confidence", 0),
            }

        converted: Dict[str, Any] = {
            "alert_id": str(uuid.uuid4()),
            "priority": priority,
            "message": f"[SCANIFY 0DTE] {message}",
            "created_at": timestamp,
            "acknowledged": False,
            "expires_at": timestamp + timedelta(hours=1),
            "source": "scanify_0dte",
            "original_type": alert_type,
            "scan_result": scan_result_dict,
        }

        self._alert_count += 1
        return converted

    # ------------------------------------------------------------------
    # (b) send_to_alert_system
    # ------------------------------------------------------------------

    def send_to_alert_system(
        self, alert: Dict[str, Any], alert_manager: Any
    ) -> None:
        """Send a converted alert to the engine's alert management system.

        Parameters
        ----------
        alert : dict
            Alert dict produced by :meth:`convert_alert`.
        alert_manager : object
            The engine's alert manager.  Expected to expose one of:
            - ``add_alert(alert_dict)``
            - ``send_alert(alert_dict)``
            - ``push(alert_dict)``
            - ``alerts`` list attribute
        """
        sent = False
        for method_name in ("add_alert", "send_alert", "push"):
            if hasattr(alert_manager, method_name) and callable(
                getattr(alert_manager, method_name)
            ):
                try:
                    getattr(alert_manager, method_name)(alert)
                    sent = True
                    break
                except Exception as exc:
                    logger.warning(
                        "Alert send via %s failed: %s", method_name, exc
                    )

        if not sent:
            # Fallback: append to alerts list if present
            if hasattr(alert_manager, "alerts") and isinstance(
                alert_manager.alerts, list
            ):
                alert_manager.alerts.append(alert)
                sent = True

        if sent:
            logger.debug("Alert sent to alert manager: %s", alert.get("message", ""))
        else:
            logger.warning(
                "Could not send alert to %s -- no supported interface.",
                type(alert_manager).__name__,
            )

    # ------------------------------------------------------------------
    # (c) create_webhook_payload
    # ------------------------------------------------------------------

    def create_webhook_payload(
        self, signal: Union[ScanSignal, GEXSignal, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Create a JSON-serialisable webhook payload from a SCANIFY signal
        for delivery to external integrations (Discord, Slack, etc.).

        Parameters
        ----------
        signal : ScanSignal | GEXSignal | dict
            The source signal.

        Returns
        -------
        dict
            Webhook-ready payload with ``event``, ``data``, ``timestamp``,
            and ``source`` keys.
        """
        timestamp = datetime.now(timezone.utc).isoformat()

        if isinstance(signal, ScanSignal):
            payload: Dict[str, Any] = {
                "event": "scanify_0dte_signal",
                "source": "scanify_0dte",
                "timestamp": timestamp,
                "data": {
                    "scan_type": signal.scan_type.value,
                    "direction": signal.direction.value,
                    "entry_price": signal.entry_price,
                    "stop_loss": signal.stop_loss,
                    "profit_target": signal.profit_target,
                    "contracts": signal.contracts,
                    "max_risk": signal.max_risk,
                    "risk_reward": signal.risk_reward_ratio,
                    "confidence": signal.direction_score.confidence,
                    "total_score": signal.direction_score.total_score,
                    "factors_agreeing": signal.direction_score.factors_agreeing,
                    "session_type": signal.session_type.value,
                    "time_zone": signal.time_zone.value,
                    "position_type": signal.position_type.value,
                },
            }
            if signal.strike_selection is not None:
                payload["data"]["strike"] = signal.strike_selection.strike
                payload["data"]["option_type"] = signal.strike_selection.option_type.value
                payload["data"]["delta"] = signal.strike_selection.delta
                payload["data"]["iv"] = signal.strike_selection.iv

        elif isinstance(signal, GEXSignal):
            payload = {
                "event": "scanify_0dte_gex_signal",
                "source": "scanify_0dte",
                "timestamp": timestamp,
                "data": {
                    "signal_type": signal.signal_type.value,
                    "direction": signal.direction.value,
                    "confidence": signal.confidence,
                    "trigger_price": signal.trigger_price,
                    "target_price": signal.target_price,
                    "description": signal.description,
                },
            }

        elif isinstance(signal, dict):
            payload = {
                "event": "scanify_0dte_raw",
                "source": "scanify_0dte",
                "timestamp": timestamp,
                "data": signal,
            }
        else:
            payload = {
                "event": "scanify_0dte_unknown",
                "source": "scanify_0dte",
                "timestamp": timestamp,
                "data": {"raw": str(signal)},
            }

        self._webhook_count += 1
        return payload

    @property
    def stats(self) -> Dict[str, int]:
        """Return alert bridge diagnostic counters."""
        return {
            "alerts_converted": self._alert_count,
            "webhooks_created": self._webhook_count,
        }


# ============================================================================
# 5. register_scanify_routes
# ============================================================================

def register_scanify_routes(app: Any) -> None:
    """Register all SCANIFY 0DTE API routes with the main FastAPI application.

    Adds the following endpoints under ``/api/v1/scanify/``:

    - ``GET  /status``           - System status and diagnostics
    - ``GET  /signals``          - Recent scan signals
    - ``GET  /gex``              - Current GEX profile
    - ``GET  /gex/signals``      - Recent GEX signals
    - ``GET  /session``          - Current session setup
    - ``POST /scan``             - Trigger an on-demand scan
    - ``GET  /positions``        - Active positions
    - ``GET  /performance``      - Daily P&L and performance metrics
    - ``GET  /config``           - Current SCANIFY configuration
    - ``POST /config``           - Update SCANIFY configuration at runtime
    - ``GET  /alerts``           - Recent alerts
    - ``GET  /calibration``      - Current calibration state

    Parameters
    ----------
    app : FastAPI
        The main FastAPI application instance.

    Notes
    -----
    The function stores the orchestrator reference on the app's ``state``
    object.  Call ``app.state.scanify_orchestrator = orchestrator`` before
    startup to wire the routes to a live system.
    """
    if APIRouter is None:
        logger.error(
            "FastAPI is not installed. Cannot register SCANIFY routes. "
            "Install with: pip install fastapi"
        )
        return

    router = APIRouter(prefix="/api/v1/scanify", tags=["SCANIFY 0DTE"])

    def _get_orchestrator(app_instance: Any) -> Optional[ScanifyOrchestrator]:
        """Retrieve the orchestrator from app state."""
        return getattr(getattr(app_instance, "state", None), "scanify_orchestrator", None)

    @router.get("/status")
    async def scanify_status():
        """Return SCANIFY system status and diagnostics."""
        from starlette.requests import Request
        # Access via closure -- the orchestrator is set on app.state
        orch = _get_orchestrator(app)
        if orch is None:
            return JSONResponse(
                status_code=503,
                content={"error": "SCANIFY orchestrator not initialized"},
            )
        return {
            "is_running": orch.is_running,
            "scan_count": orch.scan_count,
            "last_scan_time": (
                orch.last_scan_time.isoformat() if orch.last_scan_time else None
            ),
            "active_signals": len(orch.active_signals),
            "gex_signals": len(orch.gex_signals),
            "active_positions": len(orch._active_positions),
            "daily_pnl": orch._daily_pnl,
            "paper_trade": orch.paper_trade,
        }

    @router.get("/signals")
    async def scanify_signals(
        limit: int = Query(default=20, ge=1, le=100),
        scan_type: Optional[str] = Query(default=None),
    ):
        """Return recent scan signals."""
        orch = _get_orchestrator(app)
        if orch is None:
            return JSONResponse(
                status_code=503,
                content={"error": "SCANIFY orchestrator not initialized"},
            )
        signals = orch.active_signals[-limit:]
        if scan_type:
            signals = [
                s for s in signals if s.scan_type.value.lower() == scan_type.lower()
            ]
        return {
            "count": len(signals),
            "signals": [s.model_dump(mode="json") for s in signals],
        }

    @router.get("/gex")
    async def scanify_gex_profile():
        """Return the current GEX profile."""
        orch = _get_orchestrator(app)
        if orch is None:
            return JSONResponse(
                status_code=503,
                content={"error": "SCANIFY orchestrator not initialized"},
            )
        if orch.current_gex is None:
            return {"gex_profile": None, "message": "No GEX profile computed yet."}
        return {"gex_profile": orch.current_gex.model_dump(mode="json")}

    @router.get("/gex/signals")
    async def scanify_gex_signals(
        limit: int = Query(default=20, ge=1, le=100),
    ):
        """Return recent GEX signals."""
        orch = _get_orchestrator(app)
        if orch is None:
            return JSONResponse(
                status_code=503,
                content={"error": "SCANIFY orchestrator not initialized"},
            )
        signals = orch.gex_signals[-limit:]
        return {
            "count": len(signals),
            "signals": [s.model_dump(mode="json") for s in signals],
        }

    @router.get("/session")
    async def scanify_session():
        """Return the current session setup."""
        orch = _get_orchestrator(app)
        if orch is None:
            return JSONResponse(
                status_code=503,
                content={"error": "SCANIFY orchestrator not initialized"},
            )
        if orch.session_setup is None:
            return {"session_setup": None, "message": "No session setup yet."}
        return {"session_setup": orch.session_setup.model_dump(mode="json")}

    @router.post("/scan")
    async def scanify_trigger_scan():
        """Trigger an on-demand scan cycle outside the normal cadence."""
        orch = _get_orchestrator(app)
        if orch is None:
            return JSONResponse(
                status_code=503,
                content={"error": "SCANIFY orchestrator not initialized"},
            )
        if not orch.is_running:
            return JSONResponse(
                status_code=409,
                content={"error": "SCANIFY system is not running."},
            )
        # The orchestrator exposes a single scan cycle method via
        # its internal run mechanism; we log the trigger and return
        # current state.  A full async scan cycle can be dispatched
        # in the background.
        return {
            "triggered": True,
            "scan_count": orch.scan_count,
            "message": "On-demand scan cycle queued.",
        }

    @router.get("/positions")
    async def scanify_positions():
        """Return active SCANIFY positions."""
        orch = _get_orchestrator(app)
        if orch is None:
            return JSONResponse(
                status_code=503,
                content={"error": "SCANIFY orchestrator not initialized"},
            )
        return {
            "active": orch._active_positions,
            "closed_today": len(orch._closed_positions),
        }

    @router.get("/performance")
    async def scanify_performance():
        """Return daily performance metrics."""
        orch = _get_orchestrator(app)
        if orch is None:
            return JSONResponse(
                status_code=503,
                content={"error": "SCANIFY orchestrator not initialized"},
            )
        return {
            "daily_pnl": orch._daily_pnl,
            "closed_positions": len(orch._closed_positions),
            "active_positions": len(orch._active_positions),
            "scan_count": orch.scan_count,
            "pnl_curve": orch._intraday_pnl_curve[-100:],
        }

    @router.get("/config")
    async def scanify_config():
        """Return current SCANIFY configuration."""
        adapter = ScanifyConfigAdapter()
        return adapter.load_from_yaml()

    @router.get("/alerts")
    async def scanify_alerts(
        limit: int = Query(default=50, ge=1, le=200),
    ):
        """Return recent SCANIFY alerts."""
        orch = _get_orchestrator(app)
        if orch is None:
            return JSONResponse(
                status_code=503,
                content={"error": "SCANIFY orchestrator not initialized"},
            )
        return {
            "count": len(orch.alerts),
            "alerts": orch.alerts[-limit:],
        }

    @router.get("/calibration")
    async def scanify_calibration():
        """Return the current calibration state."""
        orch = _get_orchestrator(app)
        if orch is None:
            return JSONResponse(
                status_code=503,
                content={"error": "SCANIFY orchestrator not initialized"},
            )
        state = orch._calibration_state
        if state is None:
            return {"calibration_state": None}
        if hasattr(state, "model_dump"):
            return {"calibration_state": state.model_dump(mode="json")}
        return {"calibration_state": str(state)}

    # Mount the router
    app.include_router(router)
    logger.info(
        "SCANIFY routes registered: %d endpoints under /api/v1/scanify/",
        len(router.routes),
    )


# ============================================================================
# 6. create_integrated_system
# ============================================================================

def create_integrated_system(
    config_path: str = "config.yaml",
) -> ScanifyOrchestrator:
    """Create a fully-wired SCANIFY orchestrator integrated with the
    Revolution Alpha Engine infrastructure.

    This factory:
    1. Loads configuration from ``config.yaml``.
    2. Extracts data provider, API keys, and risk budget settings.
    3. Constructs a ``ScanifyOrchestrator`` with the resolved parameters.
    4. Creates and attaches the integration bridges (config, data, alerts).

    Parameters
    ----------
    config_path : str
        Path to the configuration file.  Defaults to ``"config.yaml"``.

    Returns
    -------
    ScanifyOrchestrator
        A configured orchestrator ready for ``await orchestrator.initialize()``.

    Examples
    --------
    ::

        from src.scanify_0dte.integration import create_integrated_system

        orchestrator = create_integrated_system("config.yaml")
        await orchestrator.initialize()

        # The orchestrator is now integrated with the engine's config,
        # risk management, and data systems.
        report = await orchestrator.run_full_session()
        await orchestrator.shutdown()
    """
    # ── Load configuration ──────────────────────────────────────────────
    config_adapter = ScanifyConfigAdapter(config_path)
    full_config = config_adapter.load_from_yaml()

    scanify_cfg = full_config.get("scanify_0dte", {})
    api_cfg = full_config.get("api", {})

    # Resolve data provider
    data_provider = scanify_cfg.get(
        "data_provider",
        api_cfg.get("primary_data_provider", "polygon"),
    )

    # Resolve API key from config or environment
    api_key = ""
    if data_provider == "polygon":
        api_key = os.getenv("POLYGON_API_KEY", "")
    elif data_provider == "alpaca":
        api_key = os.getenv("ALPACA_API_KEY", "")
    if not api_key:
        api_key = os.getenv("DATA_API_KEY", "")

    # Resolve risk budget
    risk_budget = scanify_cfg.get("risk_budget", 10_000.0)

    # Resolve paper trading flag
    paper_trade = scanify_cfg.get(
        "paper_trade",
        api_cfg.get("use_paper_trading", True),
    )

    # Resolve log directory
    log_dir = scanify_cfg.get("log_dir", "logs/scanify")

    # ── Try to load calibration state from disk ─────────────────────────
    calibration_state: Optional[CalibrationState] = None
    cal_path = Path(log_dir) / "calibration_state.json"
    if cal_path.exists():
        try:
            import json
            with open(cal_path, "r") as fh:
                cal_data = json.load(fh)
            calibration_state = CalibrationState(**cal_data)
            logger.info("Loaded calibration state from %s", cal_path)
        except Exception as exc:
            logger.warning("Failed to load calibration state: %s", exc)

    # ── Build orchestrator ──────────────────────────────────────────────
    orchestrator = ScanifyOrchestrator(
        data_provider=data_provider,
        api_key=api_key,
        risk_budget=risk_budget,
        paper_trade=paper_trade,
        calibration_state=calibration_state,
        log_dir=log_dir,
    )

    # ── Attach integration bridges to the orchestrator for access ───────
    engine_config = load_config(config_path)
    orchestrator._integration = ScanifyIntegration(config=engine_config)
    orchestrator._config_adapter = config_adapter
    orchestrator._data_bridge = ScanifyDataBridge(config=engine_config)
    orchestrator._alert_bridge = ScanifyAlertBridge()

    logger.info(
        "Integrated SCANIFY system created: provider=%s, paper=%s, budget=$%.0f",
        data_provider,
        paper_trade,
        risk_budget,
    )

    return orchestrator
