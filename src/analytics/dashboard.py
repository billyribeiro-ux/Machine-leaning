"""
Revolution Alpha Engine - Interactive Trading Dashboard

Professional terminal-based dashboard with:
- Real-time portfolio monitoring
- Live scanner signals
- Customizable risk parameters
- Performance analytics
- Interactive controls
"""

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.live import Live
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.text import Text
from rich.style import Style
from rich.tree import Tree
from rich.columns import Columns
from rich.prompt import Prompt, Confirm, FloatPrompt, IntPrompt
from rich.markdown import Markdown
from rich import box
import pandas as pd
import numpy as np
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
import asyncio
import logging
from collections import deque
import json

logger = logging.getLogger(__name__)


class DashboardTheme(str, Enum):
    """Dashboard color themes."""
    DARK = "dark"
    LIGHT = "light"
    PROFESSIONAL = "professional"


@dataclass
class DashboardConfig:
    """Dashboard configuration with customizable parameters."""
    # Display settings
    theme: DashboardTheme = DashboardTheme.PROFESSIONAL
    refresh_rate: float = 1.0
    max_signals_display: int = 20
    max_trades_display: int = 50

    # Risk parameters (customizable)
    risk_per_trade_pct: float = 1.0
    max_position_pct: float = 20.0
    max_portfolio_heat: float = 6.0
    max_drawdown_pct: float = 20.0
    stop_loss_atr_mult: float = 2.0
    take_profit_rr: float = 2.0

    # Scanner settings
    min_confidence: float = 60.0
    enabled_scanners: List[str] = field(default_factory=lambda: ["all"])

    # Alerts
    alert_on_signal: bool = True
    alert_on_trade: bool = True
    sound_alerts: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            'theme': self.theme.value,
            'refresh_rate': self.refresh_rate,
            'risk_per_trade_pct': self.risk_per_trade_pct,
            'max_position_pct': self.max_position_pct,
            'max_portfolio_heat': self.max_portfolio_heat,
            'max_drawdown_pct': self.max_drawdown_pct,
            'stop_loss_atr_mult': self.stop_loss_atr_mult,
            'take_profit_rr': self.take_profit_rr,
            'min_confidence': self.min_confidence,
        }


@dataclass
class PortfolioState:
    """Current portfolio state for display."""
    total_equity: float = 0
    cash: float = 0
    positions_value: float = 0
    unrealized_pnl: float = 0
    realized_pnl: float = 0
    day_pnl: float = 0
    open_positions: int = 0
    portfolio_heat: float = 0
    current_drawdown: float = 0
    max_drawdown: float = 0


@dataclass
class SignalDisplay:
    """Signal for dashboard display."""
    timestamp: datetime
    symbol: str
    direction: str
    confidence: float
    entry_price: float
    stop_loss: float
    take_profit: float
    scanner_type: str
    primary_reason: str


class DashboardColors:
    """Color schemes for dashboard."""

    @staticmethod
    def get_colors(theme: DashboardTheme) -> Dict[str, str]:
        if theme == DashboardTheme.DARK:
            return {
                'profit': 'green',
                'loss': 'red',
                'neutral': 'white',
                'header': 'bold cyan',
                'highlight': 'yellow',
                'warning': 'orange3',
                'critical': 'red bold',
                'long': 'green',
                'short': 'red',
                'panel_border': 'blue',
            }
        elif theme == DashboardTheme.LIGHT:
            return {
                'profit': 'green4',
                'loss': 'red3',
                'neutral': 'black',
                'header': 'bold blue',
                'highlight': 'orange3',
                'warning': 'yellow4',
                'critical': 'red3 bold',
                'long': 'green4',
                'short': 'red3',
                'panel_border': 'blue3',
            }
        else:  # Professional
            return {
                'profit': 'green3',
                'loss': 'red',
                'neutral': 'grey74',
                'header': 'bold bright_white',
                'highlight': 'bright_yellow',
                'warning': 'yellow',
                'critical': 'bright_red bold',
                'long': 'bright_green',
                'short': 'bright_red',
                'panel_border': 'bright_blue',
            }


class RevolutionDashboard:
    """
    Main interactive trading dashboard.

    Provides comprehensive real-time monitoring with customizable settings.
    """

    def __init__(self, config: Optional[DashboardConfig] = None):
        self.config = config or DashboardConfig()
        self.console = Console()
        self.colors = DashboardColors.get_colors(self.config.theme)

        # State
        self.portfolio = PortfolioState()
        self.signals: deque = deque(maxlen=self.config.max_signals_display)
        self.recent_trades: deque = deque(maxlen=self.config.max_trades_display)
        self.performance_history: List[Tuple[datetime, float]] = []

        # Scanner stats
        self.scanner_stats: Dict[str, Dict] = {}

        # Alerts
        self.alerts: deque = deque(maxlen=50)

        # Running state
        self._running = False
        self._last_update = datetime.now(timezone.utc)

    def create_header(self) -> Panel:
        """Create dashboard header."""
        title = Text()
        title.append("⚡ ", style="bright_yellow")
        title.append("REVOLUTION ALPHA ENGINE", style="bold bright_white")
        title.append(" ⚡", style="bright_yellow")

        subtitle = Text()
        subtitle.append("Institutional-Grade Trading System", style="italic grey50")

        header_text = Text.assemble(
            title, "\n", subtitle, "\n",
            Text(f"Last Update: {self._last_update.strftime('%H:%M:%S')}", style="dim")
        )

        return Panel(
            header_text,
            box=box.DOUBLE,
            border_style=self.colors['panel_border'],
            padding=(0, 2)
        )

    def create_portfolio_panel(self) -> Panel:
        """Create portfolio overview panel."""
        p = self.portfolio

        # Build content
        grid = Table.grid(padding=(0, 2))
        grid.add_column(justify="right", style="bold")
        grid.add_column(justify="left")

        # Equity
        grid.add_row("Total Equity:", f"${p.total_equity:,.2f}")

        # P&L with colors
        day_pnl_style = self.colors['profit'] if p.day_pnl >= 0 else self.colors['loss']
        day_pnl_pct = (p.day_pnl / (p.total_equity - p.day_pnl)) * 100 if p.total_equity != p.day_pnl else 0
        grid.add_row(
            "Day P&L:",
            Text(f"${p.day_pnl:+,.2f} ({day_pnl_pct:+.2f}%)", style=day_pnl_style)
        )

        unreal_style = self.colors['profit'] if p.unrealized_pnl >= 0 else self.colors['loss']
        grid.add_row(
            "Unrealized:",
            Text(f"${p.unrealized_pnl:+,.2f}", style=unreal_style)
        )

        # Positions
        grid.add_row("Open Positions:", f"{p.open_positions}")

        # Risk metrics
        heat_style = self.colors['warning'] if p.portfolio_heat > 4 else self.colors['neutral']
        grid.add_row("Portfolio Heat:", Text(f"{p.portfolio_heat:.1f}%", style=heat_style))

        dd_style = self.colors['critical'] if p.current_drawdown > 10 else self.colors['neutral']
        grid.add_row("Drawdown:", Text(f"{p.current_drawdown:.2f}%", style=dd_style))

        return Panel(
            grid,
            title="[bold]📊 Portfolio[/bold]",
            box=box.ROUNDED,
            border_style=self.colors['panel_border']
        )

    def create_signals_table(self) -> Panel:
        """Create live signals table."""
        table = Table(
            box=box.SIMPLE,
            show_header=True,
            header_style=self.colors['header'],
            expand=True
        )

        table.add_column("Time", width=8)
        table.add_column("Symbol", width=8)
        table.add_column("Dir", width=5)
        table.add_column("Conf", width=6)
        table.add_column("Entry", width=10)
        table.add_column("Stop", width=10)
        table.add_column("Target", width=10)
        table.add_column("Scanner", width=12)

        for signal in list(self.signals)[-10:]:
            dir_style = self.colors['long'] if signal.direction == "LONG" else self.colors['short']

            conf_style = self.colors['profit'] if signal.confidence >= 75 else (
                self.colors['warning'] if signal.confidence >= 60 else self.colors['neutral']
            )

            table.add_row(
                signal.timestamp.strftime("%H:%M"),
                signal.symbol,
                Text(signal.direction[:1], style=dir_style),
                Text(f"{signal.confidence:.0f}%", style=conf_style),
                f"${signal.entry_price:.2f}",
                f"${signal.stop_loss:.2f}",
                f"${signal.take_profit:.2f}",
                signal.scanner_type[:10],
            )

        return Panel(
            table,
            title="[bold]🎯 Live Signals[/bold]",
            box=box.ROUNDED,
            border_style=self.colors['panel_border']
        )

    def create_scanner_status(self) -> Panel:
        """Create scanner status panel."""
        tree = Tree("🔍 [bold]Active Scanners[/bold]")

        scanners = [
            ("Options Flow", "options_flow", "🎰"),
            ("Short Squeeze", "short_squeeze", "🚀"),
            ("Gamma Squeeze", "gamma_squeeze", "⚡"),
            ("Momentum", "momentum", "📈"),
            ("Reversal", "reversal", "🔄"),
            ("Breakout", "breakout", "💥"),
        ]

        for name, key, emoji in scanners:
            stats = self.scanner_stats.get(key, {})
            signals_found = stats.get('signals', 0)
            last_signal = stats.get('last_signal', 'N/A')

            status = "✅" if stats.get('active', True) else "❌"
            branch = tree.add(f"{emoji} {name} {status}")
            branch.add(f"Signals: {signals_found}")

        return Panel(
            tree,
            title="[bold]Scanner Status[/bold]",
            box=box.ROUNDED,
            border_style=self.colors['panel_border']
        )

    def create_risk_panel(self) -> Panel:
        """Create risk management settings panel."""
        config = self.config

        grid = Table.grid(padding=(0, 2))
        grid.add_column(justify="left", style="bold")
        grid.add_column(justify="right")

        grid.add_row("Risk/Trade:", f"{config.risk_per_trade_pct:.1f}%")
        grid.add_row("Max Position:", f"{config.max_position_pct:.1f}%")
        grid.add_row("Max Heat:", f"{config.max_portfolio_heat:.1f}%")
        grid.add_row("Max Drawdown:", f"{config.max_drawdown_pct:.1f}%")
        grid.add_row("Stop ATR Mult:", f"{config.stop_loss_atr_mult:.1f}x")
        grid.add_row("R:R Target:", f"{config.take_profit_rr:.1f}:1")
        grid.add_row("Min Confidence:", f"{config.min_confidence:.0f}%")

        return Panel(
            grid,
            title="[bold]⚙️ Risk Settings[/bold]",
            box=box.ROUNDED,
            border_style=self.colors['panel_border'],
            subtitle="[dim]Press 'r' to modify[/dim]"
        )

    def create_performance_panel(self) -> Panel:
        """Create performance metrics panel."""
        # Calculate metrics from history
        if len(self.performance_history) < 2:
            content = Text("Collecting data...", style="dim italic")
        else:
            returns = []
            for i in range(1, len(self.performance_history)):
                prev = self.performance_history[i-1][1]
                curr = self.performance_history[i][1]
                if prev > 0:
                    returns.append((curr - prev) / prev)

            if returns:
                total_return = (self.performance_history[-1][1] / self.performance_history[0][1] - 1) * 100
                sharpe = np.sqrt(252) * np.mean(returns) / (np.std(returns) + 1e-8)
                win_rate = sum(1 for r in returns if r > 0) / len(returns) * 100

                grid = Table.grid(padding=(0, 2))
                grid.add_column(justify="left", style="bold")
                grid.add_column(justify="right")

                ret_style = self.colors['profit'] if total_return > 0 else self.colors['loss']
                grid.add_row("Total Return:", Text(f"{total_return:+.2f}%", style=ret_style))
                grid.add_row("Sharpe Ratio:", f"{sharpe:.2f}")
                grid.add_row("Win Rate:", f"{win_rate:.1f}%")

                content = grid
            else:
                content = Text("Collecting data...", style="dim italic")

        return Panel(
            content,
            title="[bold]📈 Performance[/bold]",
            box=box.ROUNDED,
            border_style=self.colors['panel_border']
        )

    def create_alerts_panel(self) -> Panel:
        """Create alerts panel."""
        if not self.alerts:
            content = Text("No alerts", style="dim italic")
        else:
            table = Table(box=None, show_header=False, padding=(0, 1))
            table.add_column("Time", width=8)
            table.add_column("Alert")

            for alert in list(self.alerts)[-5:]:
                time_str = alert['time'].strftime("%H:%M:%S")
                level = alert.get('level', 'info')

                if level == 'critical':
                    style = self.colors['critical']
                elif level == 'warning':
                    style = self.colors['warning']
                else:
                    style = self.colors['neutral']

                table.add_row(time_str, Text(alert['message'], style=style))

            content = table

        return Panel(
            content,
            title="[bold]🔔 Alerts[/bold]",
            box=box.ROUNDED,
            border_style=self.colors['panel_border']
        )

    def create_layout(self) -> Layout:
        """Create main dashboard layout."""
        layout = Layout()

        layout.split(
            Layout(name="header", size=5),
            Layout(name="body"),
            Layout(name="footer", size=3)
        )

        layout["body"].split_row(
            Layout(name="left", ratio=1),
            Layout(name="center", ratio=2),
            Layout(name="right", ratio=1)
        )

        layout["left"].split(
            Layout(name="portfolio"),
            Layout(name="risk"),
        )

        layout["center"].split(
            Layout(name="signals", ratio=2),
            Layout(name="performance"),
        )

        layout["right"].split(
            Layout(name="scanners"),
            Layout(name="alerts"),
        )

        return layout

    def render(self) -> Layout:
        """Render complete dashboard."""
        layout = self.create_layout()

        layout["header"].update(self.create_header())
        layout["portfolio"].update(self.create_portfolio_panel())
        layout["risk"].update(self.create_risk_panel())
        layout["signals"].update(self.create_signals_table())
        layout["performance"].update(self.create_performance_panel())
        layout["scanners"].update(self.create_scanner_status())
        layout["alerts"].update(self.create_alerts_panel())

        # Footer
        footer = Text()
        footer.append(" [Q]uit ", style="bold white on dark_blue")
        footer.append(" ")
        footer.append(" [R]isk Settings ", style="bold white on dark_green")
        footer.append(" ")
        footer.append(" [S]canner Config ", style="bold white on dark_red")
        footer.append(" ")
        footer.append(" [E]xport Report ", style="bold white on dark_magenta")
        footer.append(" ")
        footer.append(" [H]elp ", style="bold white on grey50")

        layout["footer"].update(Panel(footer, box=box.SIMPLE))

        self._last_update = datetime.now(timezone.utc)
        return layout

    def add_signal(self, signal: SignalDisplay):
        """Add new signal to display."""
        self.signals.append(signal)

        if self.config.alert_on_signal and signal.confidence >= self.config.min_confidence:
            self.add_alert(
                f"{signal.direction} signal: {signal.symbol} ({signal.confidence:.0f}%)",
                level="info"
            )

    def add_alert(self, message: str, level: str = "info"):
        """Add alert to display."""
        self.alerts.append({
            'time': datetime.now(timezone.utc),
            'message': message,
            'level': level
        })

    def update_portfolio(self, state: PortfolioState):
        """Update portfolio state."""
        self.portfolio = state
        self.performance_history.append((datetime.now(timezone.utc), state.total_equity))

    def update_scanner_stats(self, scanner: str, stats: Dict):
        """Update scanner statistics."""
        self.scanner_stats[scanner] = stats


class RiskSettingsMenu:
    """Interactive risk settings configuration menu."""

    def __init__(self, console: Console, config: DashboardConfig):
        self.console = console
        self.config = config

    def show(self) -> DashboardConfig:
        """Display and modify risk settings."""
        self.console.clear()
        self.console.print(Panel(
            "[bold]Risk Management Configuration[/bold]\n"
            "Customize your risk parameters",
            box=box.DOUBLE,
            border_style="bright_blue"
        ))

        settings = [
            ("risk_per_trade_pct", "Risk per Trade (%)", 0.1, 5.0, 0.1),
            ("max_position_pct", "Max Position Size (%)", 5.0, 50.0, 5.0),
            ("max_portfolio_heat", "Max Portfolio Heat (%)", 2.0, 20.0, 2.0),
            ("max_drawdown_pct", "Max Drawdown (%)", 5.0, 50.0, 5.0),
            ("stop_loss_atr_mult", "Stop Loss ATR Multiplier", 0.5, 5.0, 0.5),
            ("take_profit_rr", "Take Profit R:R", 1.0, 5.0, 0.5),
            ("min_confidence", "Min Signal Confidence (%)", 50.0, 90.0, 5.0),
        ]

        for attr, name, min_val, max_val, step in settings:
            current = getattr(self.config, attr)
            self.console.print(f"\n[bold]{name}[/bold] (current: {current})")
            self.console.print(f"  Range: {min_val} - {max_val}")

            try:
                new_val = FloatPrompt.ask(
                    f"  Enter new value (or press Enter to keep {current})",
                    default=str(current)
                )
                new_val = float(new_val)
                new_val = max(min_val, min(max_val, new_val))
                setattr(self.config, attr, new_val)
                self.console.print(f"  ✓ Set to {new_val}", style="green")
            except:
                self.console.print(f"  Keeping {current}", style="dim")

        self.console.print("\n[bold green]Settings updated![/bold green]")

        if Confirm.ask("Save settings to file?"):
            self._save_settings()

        return self.config

    def _save_settings(self):
        """Save settings to JSON file."""
        try:
            with open("risk_config.json", "w") as f:
                json.dump(self.config.to_dict(), f, indent=2)
            self.console.print("Settings saved to risk_config.json", style="green")
        except Exception as e:
            self.console.print(f"Failed to save: {e}", style="red")


class BacktestDashboard:
    """
    Interactive dashboard for backtesting with customizable parameters.
    """

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()

    def configure_backtest(self) -> Dict[str, Any]:
        """Interactive backtest configuration."""
        self.console.clear()
        self.console.print(Panel(
            "[bold]Backtest Configuration[/bold]\n"
            "Configure your backtest parameters",
            box=box.DOUBLE,
            border_style="bright_cyan"
        ))

        config = {}

        # Date range
        self.console.print("\n[bold]📅 Date Range[/bold]")
        config['start_date'] = Prompt.ask("Start date (YYYY-MM-DD)", default="2023-01-01")
        config['end_date'] = Prompt.ask("End date (YYYY-MM-DD)", default="2024-01-01")

        # Capital
        self.console.print("\n[bold]💰 Capital Settings[/bold]")
        config['initial_capital'] = float(Prompt.ask("Initial capital ($)", default="100000"))

        # Risk settings
        self.console.print("\n[bold]⚠️ Risk Parameters[/bold]")
        config['risk_per_trade'] = float(Prompt.ask("Risk per trade (%)", default="1.0"))
        config['max_position'] = float(Prompt.ask("Max position size (%)", default="20.0"))
        config['max_drawdown'] = float(Prompt.ask("Max drawdown halt (%)", default="20.0"))

        # Commission and slippage
        self.console.print("\n[bold]💸 Costs[/bold]")
        config['commission'] = float(Prompt.ask("Commission per share ($)", default="0.005"))
        config['slippage'] = float(Prompt.ask("Slippage (%)", default="0.05"))

        # Scanner selection
        self.console.print("\n[bold]🔍 Scanners to Use[/bold]")
        scanners = ["momentum", "reversal", "breakout", "options", "squeeze"]
        for i, s in enumerate(scanners, 1):
            self.console.print(f"  {i}. {s}")

        selected = Prompt.ask("Select scanners (comma-separated, or 'all')", default="all")
        if selected.lower() == 'all':
            config['scanners'] = scanners
        else:
            indices = [int(x.strip()) - 1 for x in selected.split(',') if x.strip().isdigit()]
            config['scanners'] = [scanners[i] for i in indices if 0 <= i < len(scanners)]

        return config

    def display_results(self, results: Any):
        """Display backtest results."""
        self.console.clear()

        # Header
        self.console.print(Panel(
            "[bold]📊 Backtest Results[/bold]",
            box=box.DOUBLE,
            border_style="bright_green"
        ))

        # Summary table
        summary = Table(title="Performance Summary", box=box.ROUNDED)
        summary.add_column("Metric", style="bold")
        summary.add_column("Value", justify="right")

        metrics = [
            ("Initial Capital", f"${results.initial_capital:,.2f}"),
            ("Final Capital", f"${results.final_capital:,.2f}"),
            ("Total Return", f"${results.total_return:,.2f} ({results.total_return_pct:.2f}%)"),
            ("Annual Return", f"{results.annual_return:.2f}%"),
            ("Max Drawdown", f"{results.max_drawdown:.2f}%"),
            ("Sharpe Ratio", f"{results.sharpe_ratio:.2f}"),
            ("Sortino Ratio", f"{results.sortino_ratio:.2f}"),
            ("Win Rate", f"{results.win_rate:.2f}%"),
            ("Profit Factor", f"{results.profit_factor:.2f}"),
            ("Total Trades", str(results.total_trades)),
        ]

        for metric, value in metrics:
            summary.add_row(metric, value)

        self.console.print(summary)

        # Trade breakdown
        self.console.print("\n")
        trades_table = Table(title="Trade Statistics", box=box.ROUNDED)
        trades_table.add_column("Metric", style="bold")
        trades_table.add_column("Winners", justify="right", style="green")
        trades_table.add_column("Losers", justify="right", style="red")

        trades_table.add_row("Count", str(results.winning_trades), str(results.losing_trades))
        trades_table.add_row("Gross P&L", f"${results.gross_profit:,.2f}", f"${results.gross_loss:,.2f}")
        trades_table.add_row("Average", f"${results.avg_win:,.2f}", f"${results.avg_loss:,.2f}")
        trades_table.add_row("Largest", f"${results.largest_win:,.2f}", f"${results.largest_loss:,.2f}")

        self.console.print(trades_table)

        # Export options
        self.console.print("\n[bold]Export Options:[/bold]")
        self.console.print("  1. Export to CSV")
        self.console.print("  2. Generate PDF Report")
        self.console.print("  3. View Trade Details")
        self.console.print("  4. Return to Dashboard")

    def display_trade_diagnostics(self, trade: Any):
        """Display detailed trade diagnostic."""
        self.console.print(Panel(
            f"[bold]Trade Analysis: {trade.symbol}[/bold]",
            box=box.DOUBLE
        ))

        if trade.diagnostic:
            self.console.print(Markdown(f"""
## Entry Reasoning

**Primary Reason:** {trade.diagnostic.primary_reason}

### Supporting Factors:
{chr(10).join(f'- {r}' for r in trade.diagnostic.secondary_reasons)}

### Technical Context
- **Trend:** {trade.diagnostic.trend_alignment}
- **Momentum:** {trade.diagnostic.momentum_status}
- **Volatility:** {trade.diagnostic.volatility_environment}

### Risk Parameters
- **Risk/Reward:** {trade.diagnostic.risk_reward_ratio:.2f}
- **Entry Quality:** {trade.diagnostic.entry_timing_quality}

### Indicators at Entry
- RSI: {trade.diagnostic.rsi_at_entry:.1f if trade.diagnostic.rsi_at_entry else 'N/A'}
- MACD: {trade.diagnostic.macd_at_entry:.4f if trade.diagnostic.macd_at_entry else 'N/A'}
- ADX: {trade.diagnostic.adx_at_entry:.1f if trade.diagnostic.adx_at_entry else 'N/A'}
            """))

        # Trade outcome
        pnl_style = "green" if trade.net_pnl > 0 else "red"
        self.console.print(f"\n[bold]Outcome:[/bold] [{pnl_style}]${trade.net_pnl:+,.2f} ({trade.pnl_pct:+.2f}%)[/{pnl_style}]")
        self.console.print(f"[bold]Exit Reason:[/bold] {trade.exit_reason}")
        self.console.print(f"[bold]R-Multiple:[/bold] {trade.r_multiple:.2f}R")
