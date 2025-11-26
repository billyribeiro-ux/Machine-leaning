# Revolution Alpha Engine
## Deployment Guide & User Manual

**Version 1.0.0**
**Institutional-Grade ML Trading System**

---

# Table of Contents

1. [Introduction](#introduction)
2. [System Requirements](#system-requirements)
3. [Installation](#installation)
4. [Configuration](#configuration)
5. [Quick Start](#quick-start)
6. [Architecture Overview](#architecture-overview)
7. [Module Reference](#module-reference)
8. [User Guide](#user-guide)
9. [API Reference](#api-reference)
10. [Troubleshooting](#troubleshooting)
11. [Best Practices](#best-practices)
12. [Security](#security)

---

# 1. Introduction

## What is Revolution Alpha Engine?

Revolution Alpha Engine is a state-of-the-art, institutional-grade machine learning trading system designed for professional traders, quantitative analysts, and hedge funds. It provides:

- **Real-time Market Scanning**: Multi-strategy scanners for momentum, squeeze, and options flow
- **0DTE SPX Options Trading**: Specialized system with Greeks analysis and GEX tracking
- **Self-Learning AI**: Neural networks that adapt to changing market conditions
- **Risk Management**: Comprehensive position sizing and exposure limits
- **Beautiful Dashboard**: Professional terminal UI with real-time updates

## Key Features

| Feature | Description |
|---------|-------------|
| Scanner System | Momentum, squeeze, options flow, multi-timeframe scanners |
| 0DTE Options | Complete SPX options system with all Greeks |
| Machine Learning | PyTorch-based models with online learning |
| Risk Management | Kelly criterion, VaR, position limits |
| Backtesting | Full historical testing with trade diagnostics |
| Dashboard | Rich terminal UI with live updates |

---

# 2. System Requirements

## Hardware Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU | 4 cores | 8+ cores |
| RAM | 8 GB | 32 GB |
| Storage | 20 GB SSD | 100 GB NVMe |
| Network | 10 Mbps | 100+ Mbps |

## Software Requirements

| Software | Version |
|----------|---------|
| Python | 3.11+ |
| Operating System | Linux (Ubuntu 22.04+), macOS 12+, Windows 10+ |
| Git | 2.30+ |

## Required Python Packages

```
pytorch >= 2.0.0
numpy >= 1.24.0
pandas >= 2.0.0
scikit-learn >= 1.3.0
fastapi >= 0.100.0
rich >= 13.0.0
pydantic >= 2.0.0
aiohttp >= 3.8.0
```

---

# 3. Installation

## Step 1: Clone the Repository

```bash
git clone https://github.com/billyribeiro-ux/Machine-leaning.git
cd Machine-leaning
```

## Step 2: Create Virtual Environment

```bash
# Using venv
python3.11 -m venv venv
source venv/bin/activate  # Linux/macOS
# or
venv\Scripts\activate  # Windows

# Using conda
conda create -n revolution python=3.11
conda activate revolution
```

## Step 3: Install Dependencies

```bash
# Install all dependencies
pip install -r requirements.txt

# Or install with development tools
pip install -e ".[dev]"
```

## Step 4: Verify Installation

```bash
# Run verification
python -c "import src; print('Installation successful!')"

# Run demo
python main.py --demo
```

## Step 5: Configure API Keys (Optional)

Create a `.env` file in the project root:

```bash
# Data providers
POLYGON_API_KEY=your_polygon_key
ALPACA_API_KEY=your_alpaca_key
ALPACA_SECRET_KEY=your_alpaca_secret

# Optional
OPENAI_API_KEY=your_openai_key  # For sentiment analysis
```

---

# 4. Configuration

## Configuration File Structure

Create `config.yaml` in the project root:

```yaml
# Environment
environment: development  # development, staging, production

# Trading Configuration
trading:
  symbols:
    - SPY
    - QQQ
    - SPX
  futures_symbols:
    - ES
    - NQ
  max_position_size: 100
  max_daily_trades: 50
  max_open_positions: 10

# Risk Configuration
risk:
  max_portfolio_risk_pct: 2.0
  max_position_risk_pct: 0.5
  max_daily_loss_pct: 3.0
  kelly_fraction: 0.25
  max_leverage: 2.0

# Scanner Configuration
scanner:
  scan_interval_seconds: 5
  min_volume: 100000
  min_confidence: 70.0
  min_confirmations: 3
  enable_momentum_scanner: true
  enable_squeeze_scanner: true
  enable_options_scanner: true

# ML Configuration
ml:
  model_type: ensemble
  hidden_sizes: [256, 128, 64]
  learning_rate: 0.001
  enable_online_learning: true

# Logging Configuration
logging:
  level: INFO
  log_to_file: true
  log_dir: logs

# Display Configuration
display:
  theme: dark
  refresh_rate_ms: 1000
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `REVOLUTION_ENV` | Environment name | development |
| `REVOLUTION_CONFIG` | Config file path | config.yaml |
| `POLYGON_API_KEY` | Polygon.io API key | - |
| `ALPACA_API_KEY` | Alpaca API key | - |
| `ALPACA_SECRET_KEY` | Alpaca secret key | - |

---

# 5. Quick Start

## Start with Default Settings

```bash
python main.py
```

## Start in Paper Trading Mode

```bash
python main.py --mode paper
```

## Start Dashboard Only

```bash
python main.py --dashboard
```

## Run Backtest

```bash
python main.py --mode backtest
```

## View Demo with Sample Data

```bash
python main.py --demo
```

## Command Line Options

| Option | Description |
|--------|-------------|
| `--mode` | Trading mode: live, paper, backtest |
| `--config` | Path to config file |
| `--dashboard` | Show dashboard only |
| `--scan` | Run scanner only |
| `--no-dashboard` | Run headless |
| `--demo` | Run with demo data |
| `--version` | Show version |

---

# 6. Architecture Overview

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Revolution Alpha Engine                       │
├─────────────────────────────────────────────────────────────────┤
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐   │
│  │  Scanner  │  │  Trading  │  │    ML     │  │   Risk    │   │
│  │  System   │  │  Engine   │  │  Models   │  │  Manager  │   │
│  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘   │
│        │              │              │              │          │
│        └──────────────┼──────────────┼──────────────┘          │
│                       │              │                         │
│  ┌────────────────────▼──────────────▼────────────────────┐   │
│  │                    Core Infrastructure                  │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐ │   │
│  │  │  Config  │  │ Logging  │  │Validation│  │ Cache  │ │   │
│  │  └──────────┘  └──────────┘  └──────────┘  └────────┘ │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    User Interface                        │   │
│  │  ┌──────────────────────────────────────────────────┐  │   │
│  │  │              Rich Terminal Dashboard              │  │   │
│  │  └──────────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Directory Structure

```
Machine-leaning/
├── main.py                 # Main entry point
├── config.yaml             # Configuration file
├── requirements.txt        # Dependencies
├── pyproject.toml          # Project configuration
├── docs/                   # Documentation
│   └── DEPLOYMENT_GUIDE.md
├── src/                    # Source code
│   ├── core/               # Core infrastructure
│   │   ├── config.py       # Configuration management
│   │   ├── logging.py      # Logging system
│   │   ├── validation.py   # Data validation
│   │   ├── performance.py  # Performance optimization
│   │   └── exceptions.py   # Custom exceptions
│   ├── scanner/            # Scanner system
│   │   ├── engine.py       # Scanner orchestration
│   │   ├── momentum_scanner.py
│   │   ├── squeeze_scanner.py
│   │   └── options_scanner.py
│   ├── options_0dte/       # 0DTE options system
│   │   ├── spx_engine.py   # Core 0DTE engine
│   │   ├── self_learning.py
│   │   ├── flow_analyzer.py
│   │   ├── scanner.py
│   │   └── trade_diagnostics.py
│   ├── ml/                 # Machine learning
│   ├── risk/               # Risk management
│   ├── backtest/           # Backtesting
│   └── ui/                 # User interface
│       └── dashboard.py
├── tests/                  # Test files
├── logs/                   # Log files
├── data/                   # Data storage
├── models/                 # Trained models
└── output/                 # Output files
```

---

# 7. Module Reference

## Scanner System (`src/scanner/`)

### Momentum Scanner

Detects momentum breakouts and trend continuations.

```python
from src.scanner import MomentumScanner

scanner = MomentumScanner(
    lookback_periods=[5, 10, 20],
    min_volume=100000,
    min_momentum_score=70
)

results = scanner.scan(symbols=['SPY', 'QQQ', 'AAPL'])
```

### Options Flow Scanner

Analyzes institutional options activity.

```python
from src.scanner import OptionsScanner

scanner = OptionsScanner(
    min_premium=50000,
    detect_sweeps=True,
    detect_blocks=True
)

flow = scanner.analyze_flow(options_data)
```

## 0DTE Options System (`src/options_0dte/`)

### Core Engine

```python
from src.options_0dte import ZeroDTEEngine, create_0dte_engine

# Create engine
engine = create_0dte_engine()

# Generate signal
signal = engine.generate_signal(
    spot_price=4500.0,
    options_chain=chain_df,
    flow_data=flow_df
)

# Get full reasoning
print(signal.get_full_reasoning())
```

### Self-Learning System

```python
from src.options_0dte import SelfLearningSystem

# Create system
learner = SelfLearningSystem()

# Extract features
features = learner.extract_features(
    price_data=df,
    greeks=greeks_dict,
    flow_data=flow_dict,
    gex_data=gex_dict
)

# Get prediction
prediction = learner.predict(features)
print(f"Direction: {prediction['direction']}")
print(f"Confidence: {prediction['confidence']:.1f}%")

# Learn from outcome
learner.learn_from_outcome(features, action=1, profit_pct=15.5)
```

### Flow Analyzer

```python
from src.options_0dte import InstitutionalFlowAnalyzer, create_flow_analyzer

analyzer = create_flow_analyzer()
summary = analyzer.analyze_flow(orders, period_minutes=5)

print(summary.get_full_analysis())
```

### Trade Diagnostics

```python
from src.options_0dte import TradeDiagnosticsEngine, create_diagnostics_engine

engine = create_diagnostics_engine(level='detailed')

diagnostics = engine.generate_diagnostics(
    trade_signal=signal,
    market_internals=internals,
    greeks=greeks,
    flow_data=flow,
    gex_data=gex
)

print(diagnostics.get_complete_report())
```

## Risk Management (`src/risk/`)

```python
from src.risk import RiskManager

risk_mgr = RiskManager(
    max_portfolio_risk_pct=2.0,
    max_position_risk_pct=0.5,
    kelly_fraction=0.25
)

# Calculate position size
size = risk_mgr.calculate_position_size(
    confidence=85,
    win_rate=0.65,
    avg_win=300,
    avg_loss=150,
    account_size=100000
)
```

---

# 8. User Guide

## Dashboard Overview

The dashboard displays:

1. **Market Overview**: Real-time prices for major indices
2. **Scanner Alerts**: Live signals from all scanners
3. **Open Positions**: Current portfolio with P&L
4. **Performance Metrics**: Win rate, profit factor, etc.
5. **Options Flow**: Institutional activity summary
6. **Portfolio Greeks**: Delta, gamma, theta exposure
7. **System Status**: Connection and scanner status

## Reading Scanner Alerts

| Priority | Meaning | Action |
|----------|---------|--------|
| CRITICAL | Immediate opportunity | Act within seconds |
| HIGH | Strong setup | Evaluate quickly |
| MEDIUM | Good setup | Review carefully |
| LOW | Marginal setup | Only if capital allows |

## Understanding Options Flow

| Indicator | Bullish | Bearish |
|-----------|---------|---------|
| Put/Call Ratio | < 0.7 | > 1.3 |
| Call Sweeps | High count | Low count |
| Smart Money | Bullish | Bearish |

## Greeks Guide

| Greek | What It Measures | Risk Level |
|-------|------------------|------------|
| Delta | Directional exposure | > 100 = High |
| Gamma | Rate of delta change | > 50 = High |
| Theta | Time decay | > -500/day = High |
| Vega | Volatility sensitivity | > 1000 = High |

---

# 9. API Reference

## Configuration API

```python
from src.core.config import Config, load_config, save_config

# Load configuration
config = load_config('config.yaml')

# Access settings
print(config.trading.max_position_size)
print(config.risk.max_portfolio_risk_pct)

# Modify and save
config.scanner.min_confidence = 80.0
save_config(config, 'config.yaml')
```

## Logging API

```python
from src.core.logging import (
    setup_logging,
    get_logger,
    TradeLogger,
    PerformanceLogger
)

# Setup logging
setup_logging(level='INFO', log_to_file=True)

# Get logger
logger = get_logger(__name__)
logger.info("Starting system...")

# Trade logging
trade_logger = TradeLogger()
record = trade_logger.log_entry(
    symbol='SPX 4500C',
    direction='LONG',
    quantity=5,
    price=4.50,
    stop_loss=2.25
)

# Log exit
trade_logger.log_exit(record, exit_price=6.00)

# Get statistics
stats = trade_logger.get_statistics()
```

## Validation API

```python
from src.core.validation import (
    validate_dataframe,
    validate_options_chain,
    validate_price_data,
    validate_trade_signal,
    DataQualityChecker
)

# Validate DataFrame
result = validate_dataframe(
    df,
    required_columns=['open', 'high', 'low', 'close'],
    min_rows=100
)

if not result.is_valid:
    print(result.get_report())

# Quality checker
checker = DataQualityChecker()
result = checker.check(df, 'price_data')
print(checker.get_summary())
```

---

# 10. Troubleshooting

## Common Issues

### Issue: Import Error

```
ModuleNotFoundError: No module named 'src'
```

**Solution**: Ensure you're in the project root and run:
```bash
pip install -e .
```

### Issue: API Connection Failed

```
APIConnectionError: Failed to connect to Polygon
```

**Solution**:
1. Check API key in `.env`
2. Verify network connection
3. Check API rate limits

### Issue: High Memory Usage

**Solution**:
1. Reduce `experience_replay_size` in ML config
2. Lower `memory_size` in cache settings
3. Restart application periodically

### Issue: Slow Scanning

**Solution**:
1. Increase `scan_interval_seconds`
2. Reduce number of symbols
3. Disable unused scanners

## Log Files

| File | Contains |
|------|----------|
| `logs/revolution.log` | All application logs |
| `logs/errors.log` | Errors only |
| `logs/trades.log` | Trade execution logs |
| `logs/performance.log` | Performance metrics |
| `logs/audit.log` | Security audit trail |

---

# 11. Best Practices

## Risk Management

1. **Never risk more than 2% per trade**
2. **Set daily loss limits** (recommended: 3%)
3. **Use stop losses on every position**
4. **Monitor Greeks exposure continuously**

## Trading Guidelines

1. **Start with paper trading** to learn the system
2. **Backtest strategies** before live trading
3. **Review trade diagnostics** for every trade
4. **Trust the confirmations** - more is better

## System Maintenance

1. **Update daily** with `git pull`
2. **Monitor log files** for errors
3. **Back up configuration** regularly
4. **Review performance** weekly

## Performance Optimization

1. **Use caching** for repeated calculations
2. **Enable parallel processing** for scans
3. **Optimize lookback periods** for your needs
4. **Clean old data** periodically

---

# 12. Security

## API Key Protection

- Never commit `.env` to version control
- Use environment variables in production
- Rotate keys periodically

## Network Security

- Use secure connections (HTTPS/WSS)
- Implement rate limiting
- Monitor for unusual activity

## Access Control

- Limit who can access the system
- Use audit logging
- Review access logs regularly

---

# Appendix A: Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Ctrl+C` | Exit application |
| `H` | Show help |
| `R` | Refresh display |
| `S` | Open settings |
| `P` | Pause/resume scanning |

# Appendix B: Signal Interpretations

## Market Internals

| Indicator | Bullish | Neutral | Bearish |
|-----------|---------|---------|---------|
| TRIN | < 0.9 | 0.9 - 1.1 | > 1.1 |
| TICK | > +400 | -400 to +400 | < -400 |
| ADD | > +500 | -500 to +500 | < -500 |
| UVOL/DVOL | > 1.5 | 0.67 - 1.5 | < 0.67 |

## Volatility

| VIX Level | Interpretation |
|-----------|----------------|
| < 12 | Extreme complacency |
| 12-16 | Low volatility |
| 16-20 | Normal |
| 20-25 | Elevated |
| 25-30 | High |
| > 30 | Extreme fear |

---

# Support

For issues and feature requests:
- GitHub: https://github.com/billyribeiro-ux/Machine-leaning/issues

---

**Revolution Alpha Engine** - Trade Smarter, Not Harder

*Document Version: 1.0.0*
*Last Updated: 2024*
