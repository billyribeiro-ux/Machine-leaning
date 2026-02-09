"""
SCANIFY - 0DTE SPX OTM Options Day Trading Scanner + Gamma Exposure (GEX) Scanner
==================================================================================

The Most Precise, Innovative, and Accurate Scanner System Ever Built.

This is a precision-engineered 0DTE SPX intraday trading system built on:
- Quantifiable dealer mechanics (market makers MUST delta-hedge)
- Mathematical properties of options at expiration (gamma explosion, theta acceleration, charm decay)
- Empirical data (57% of SPX options ADV is 0DTE, 2.15M contracts/day Q3 2025)
- Academic research (Bandi-Fusari-Reno 2024, Bozovic 2025, Dim-Eraker-Vilkov 2024)

Architecture
------------
The system consists of the following modules:

**Foundation Layer:**
    constants        - SPX 0DTE contract specs, time zones, thresholds, configuration defaults
    models           - Pydantic data models for all scanner data structures
    greeks_engine    - Black-Scholes pricing with 0DTE-specific Greeks (gamma, charm, vanna, speed)

**Core Engines:**
    gex_engine       - Gamma Exposure calculation engine with dealer positioning models
    data_pipeline    - Real-time data feed management (Polygon, Alpaca, mock)

**Scanner Modules (3 Core Scans):**
    pre_market_scanner    - Pre-market session setup (gap analysis, expected move, session classification)
    directional_scanner   - Core Scan #1: Directional OTM scanner (5-factor composite direction score)
    premium_scanner       - Core Scan #2: Premium selling scanner (credit spreads, iron condors)
    gamma_scalp_scanner   - Core Scan #3: Gamma scalp/acceleration scanner (final 2 hours)

**Position & Risk Management:**
    exit_manager     - Disciplined exit management (profit targets, stops, time-based, break-even)

**Intelligence & Learning:**
    calibration      - Self-learning system (daily/weekly/monthly calibration, regime detection)
    backtester       - Walk-forward backtesting framework with strict validation rules

**Orchestration:**
    orchestrator     - Main entry point tying all components together

Quick Start
-----------
```python
from src.scanify_0dte import create_scanify_system

# Create the complete system
system = create_scanify_system({
    'data_provider': 'polygon',
    'api_key': 'YOUR_KEY',
    'paper_trade': True,
    'risk_budget': 10000.0,
})

# Run a full trading session
import asyncio
report = asyncio.run(system.run_full_session())
```

Individual Component Usage
--------------------------
```python
# Greeks Engine
from src.scanify_0dte.greeks_engine import BlackScholes0DTE, GreeksCalculator

bs = BlackScholes0DTE()
greeks = bs.compute_all_greeks(S=6000, K=6050, T_minutes=120, sigma=0.15)

# GEX Engine
from src.scanify_0dte.gex_engine import GEXEngine, GEXSignalGenerator

gex = GEXEngine(bs_calculator=bs)
profile = gex.compute_full_gex_profile(chain, minutes_remaining=120)

# Pre-Market Scanner
from src.scanify_0dte.pre_market_scanner import PreMarketScanner

pre_market = PreMarketScanner(bs_calc=bs, gex_engine=gex)
setup = pre_market.run_pre_market_scan(...)

# Directional Scanner
from src.scanify_0dte.directional_scanner import DirectionalOTMScanner

scanner = DirectionalOTMScanner()
signal = scanner.scan(chain, internals, spx_price, ...)

# Premium Selling Scanner
from src.scanify_0dte.premium_scanner import PremiumSellingScanner

premium = PremiumSellingScanner()
signal = premium.scan(chain, internals, spx_price, ...)

# Gamma Scalp Scanner
from src.scanify_0dte.gamma_scalp_scanner import GammaScalpScanner

gamma = GammaScalpScanner(bs_calc=bs)
signal = gamma.scan(chain, gex_profile, spx_price, ...)

# Exit Manager
from src.scanify_0dte.exit_manager import ExitManager

exits = ExitManager(risk_budget_daily=10000)
position = exits.open_position(signal, fill_price, contracts)
actions = exits.evaluate_all_exits(...)

# Calibration
from src.scanify_0dte.calibration import DailyCalibrator, TradeLogger

logger = TradeLogger()
calibrator = DailyCalibrator(trade_logger=logger)
new_state = calibrator.run_daily_calibration(date.today())

# Backtester
from src.scanify_0dte.backtester import BacktestEngine, BacktestConfig

config = BacktestConfig(start_date=date(2024,1,1), end_date=date(2024,12,31))
engine = BacktestEngine(config=config, ...)
results = engine.run_backtest()
```

Data Sources
------------
- SPX Index: Real-time tick/1-second
- ES Futures: Price, volume, OI, Level 2 order book
- SPXW Options Chain: All 0DTE strikes, bid/ask/mid/last/volume/OI/Greeks
- VIX, VIX1D, VIX9D: Real-time 15-second
- Market Internals: NYSE TICK, TRIN, A/D, Up/Down Volume, ES Cumulative Delta
- Economic Calendar: Scheduled events with buffer windows
- Prior Session: Close, high, low, VWAP, GEX profile, 20-day RV

Academic References
-------------------
- Bandi, Fusari, Reno (2024): 0DTE pricing with jump-diffusion
- Bozovic (2025): Intraday jumps and 0DTE options
- Dim, Eraker, Vilkov (2024): Charm exposure from 0DTE options
- Baltussen, Da, Lammers, Martens (2021): Hedging demand and intraday momentum
- Albers (2025): VIX1D forecasting and risk premium
- Cboe Research: Dealer gamma impact analysis

Version: 1.0.0
Author: Revolution Alpha Engine - SCANIFY Division
License: MIT
"""

# Foundation Layer
from .constants import (
    # Contract Specifications
    SPX_CONTRACT,
    TRADING_HOURS,
    TICK_SIZES,
    MULTIPLIER,

    # Time Zones
    TIME_ZONES,
    TimeZoneConfig,

    # Thresholds
    DIRECTION_THRESHOLDS,
    FACTOR_WEIGHTS_DEFAULT,
    STRIKE_SELECTION,
    EXIT_CONSTANTS,
    LIQUIDITY_FILTERS,
    PREMIUM_SELLING_CONSTANTS,
    GEX_CONSTANTS,
    CALIBRATION_CONSTANTS,
    RISK_CONSTANTS,

    # VIX1D
    VIX1D_CONSTANTS,
)

from .models import (
    # Enums
    SessionType,
    ScanType,
    TradeDirection,
    ExitReason,
    TimeZoneType,
    GEXSignalType,
    OptionSide,
    PositionType,

    # Market Data Models
    OptionQuote,
    OptionsChain,
    MarketInternals,
    CrossAssetData,
    ESOrderBook,
    EconomicEvent,

    # GEX Models
    StrikeGEX,
    GEXProfile,
    GEXSignal,

    # Scan Result Models
    DirectionScore,
    StrikeSelection,
    ScanSignal,

    # Spread Models
    SpreadLeg,
    CreditSpread,
    IronCondor,

    # Trade Log
    TradeLog,

    # Calibration Models
    DailyScoreCard,
    FactorWeights,
    CalibrationState,

    # Pre-Market Models
    GapAnalysis,
    ExpectedMove,
    KeyLevels,
    SessionSetup,
)

# Greeks Engine
from .greeks_engine import (
    BlackScholes0DTE,
    GreeksCalculator,
    annualized_time,
    normal_pdf,
    normal_cdf,
    moneyness,
    expected_move_vix1d,
    expected_move_straddle,
    expected_move_rv_adjusted,
    composite_expected_move,
    theta_decay_fraction,
)

# GEX Engine
from .gex_engine import (
    GEXEngine,
    GEXSignalGenerator,
)

# Data Pipeline
from .data_pipeline import (
    DataFeedManager,
    MockDataProvider,
    get_trading_day_expiry,
    minutes_until_close,
    is_market_open,
    get_et_now,
)

# Scanners
from .pre_market_scanner import PreMarketScanner
from .directional_scanner import DirectionalOTMScanner
from .premium_scanner import PremiumSellingScanner
from .gamma_scalp_scanner import GammaScalpScanner

# Exit Management
from .exit_manager import ExitManager, Position

# Calibration & Learning
from .calibration import (
    TradeLogger,
    DailyCalibrator,
    WeeklyCalibrator,
    MonthlyCalibrator,
    RegimeDetector,
)

# Backtesting
from .backtester import (
    BacktestConfig,
    BacktestDataLoader,
    BacktestEngine,
    BacktestVisualizer,
)

# Orchestrator
from .orchestrator import (
    ScanifyOrchestrator,
    create_scanify_system,
)


__all__ = [
    # === Foundation ===
    'SPX_CONTRACT', 'TRADING_HOURS', 'TICK_SIZES', 'MULTIPLIER',
    'TIME_ZONES', 'TimeZoneConfig',
    'DIRECTION_THRESHOLDS', 'FACTOR_WEIGHTS_DEFAULT', 'STRIKE_SELECTION',
    'EXIT_CONSTANTS', 'LIQUIDITY_FILTERS', 'PREMIUM_SELLING_CONSTANTS',
    'GEX_CONSTANTS', 'CALIBRATION_CONSTANTS', 'RISK_CONSTANTS',
    'VIX1D_CONSTANTS',

    # === Enums ===
    'SessionType', 'ScanType', 'TradeDirection', 'ExitReason',
    'TimeZoneType', 'GEXSignalType', 'OptionSide', 'PositionType',

    # === Market Data Models ===
    'OptionQuote', 'OptionsChain', 'MarketInternals', 'CrossAssetData',
    'ESOrderBook', 'EconomicEvent',

    # === GEX Models ===
    'StrikeGEX', 'GEXProfile', 'GEXSignal',

    # === Scan Models ===
    'DirectionScore', 'StrikeSelection', 'ScanSignal',
    'SpreadLeg', 'CreditSpread', 'IronCondor',

    # === Trade & Calibration Models ===
    'TradeLog', 'DailyScoreCard', 'FactorWeights', 'CalibrationState',
    'GapAnalysis', 'ExpectedMove', 'KeyLevels', 'SessionSetup',

    # === Greeks Engine ===
    'BlackScholes0DTE', 'GreeksCalculator',
    'annualized_time', 'normal_pdf', 'normal_cdf', 'moneyness',
    'expected_move_vix1d', 'expected_move_straddle',
    'expected_move_rv_adjusted', 'composite_expected_move',
    'theta_decay_fraction',

    # === GEX Engine ===
    'GEXEngine', 'GEXSignalGenerator',

    # === Data Pipeline ===
    'DataFeedManager', 'MockDataProvider',
    'get_trading_day_expiry', 'minutes_until_close',
    'is_market_open', 'get_et_now',

    # === Scanners ===
    'PreMarketScanner', 'DirectionalOTMScanner',
    'PremiumSellingScanner', 'GammaScalpScanner',

    # === Exit Management ===
    'ExitManager', 'Position',

    # === Calibration ===
    'TradeLogger', 'DailyCalibrator', 'WeeklyCalibrator',
    'MonthlyCalibrator', 'RegimeDetector',

    # === Backtesting ===
    'BacktestConfig', 'BacktestDataLoader',
    'BacktestEngine', 'BacktestVisualizer',

    # === Orchestrator ===
    'ScanifyOrchestrator', 'create_scanify_system',
]

__version__ = '1.0.0'
__author__ = 'Revolution Alpha Engine - SCANIFY Division'
__description__ = 'SCANIFY: 0DTE SPX OTM Options Day Trading Scanner + GEX Scanner'
