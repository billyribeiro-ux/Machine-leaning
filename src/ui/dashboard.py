"""
Revolution Alpha Engine - Beautiful CLI Dashboard

State-of-the-art terminal UI using Rich library.

Features:
- Real-time market data display
- Scanner results with color coding
- Portfolio overview
- Performance metrics
- Trade history
- System status
"""

from rich.console import Console, Group
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.live import Live
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
from rich.style import Style
from rich.box import DOUBLE, ROUNDED, HEAVY
from rich.align import Align
from rich import box
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import time


# Theme colors
class Theme:
    """Dashboard color theme."""
    # Primary colors
    PROFIT = "green"
    LOSS = "red"
    NEUTRAL = "yellow"
    INFO = "cyan"
    WARNING = "yellow"
    ERROR = "red"
    SUCCESS = "green"

    # Priority colors
    CRITICAL = "bold red"
    HIGH = "bold yellow"
    MEDIUM = "cyan"
    LOW = "dim"

    # Sentiment colors
    BULLISH = "green"
    BEARISH = "red"
    NEUTRAL_SENTIMENT = "yellow"

    # UI elements
    HEADER = "bold white on blue"
    SUBHEADER = "bold cyan"
    BORDER = "blue"
    ACCENT = "magenta"


@dataclass
class MarketData:
    """Market data for display."""
    symbol: str
    price: float
    change: float
    change_pct: float
    volume: int
    high: float
    low: float


@dataclass
class ScannerAlert:
    """Scanner alert for display."""
    timestamp: datetime
    symbol: str
    alert_type: str
    direction: str
    confidence: float
    price: float
    priority: str


@dataclass
class Position:
    """Position for display."""
    symbol: str
    direction: str
    quantity: int
    entry_price: float
    current_price: float
    pnl: float
    pnl_pct: float


class DashboardComponents:
    """
    Reusable dashboard components.
    """

    @staticmethod
    def create_header() -> Panel:
        """Create the main header."""
        title = Text()
        title.append("╔══════════════════════════════════════════════════════════════════╗\n", style="bold blue")
        title.append("║           ", style="bold blue")
        title.append("REVOLUTION ALPHA ENGINE", style="bold white")
        title.append("                              ║\n", style="bold blue")
        title.append("║           ", style="bold blue")
        title.append("Institutional-Grade Trading System", style="dim white")
        title.append("                  ║\n", style="bold blue")
        title.append("╚══════════════════════════════════════════════════════════════════╝", style="bold blue")

        return Panel(
            Align.center(title),
            box=box.SIMPLE,
            style="blue"
        )

    @staticmethod
    def create_status_bar(
        status: str = "RUNNING",
        mode: str = "LIVE",
        time_str: Optional[str] = None
    ) -> Table:
        """Create status bar."""
        time_str = time_str or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        table = Table(show_header=False, box=None, expand=True)
        table.add_column(justify="left", ratio=1)
        table.add_column(justify="center", ratio=2)
        table.add_column(justify="right", ratio=1)

        status_style = Theme.SUCCESS if status == "RUNNING" else Theme.ERROR
        mode_style = Theme.WARNING if mode == "PAPER" else Theme.SUCCESS

        table.add_row(
            Text(f"● Status: {status}", style=status_style),
            Text(f"Mode: {mode}", style=mode_style),
            Text(time_str, style="dim")
        )

        return table

    @staticmethod
    def create_market_overview(markets: List[MarketData]) -> Panel:
        """Create market overview panel."""
        table = Table(
            title="📊 Market Overview",
            box=ROUNDED,
            title_style=Theme.SUBHEADER,
            expand=True
        )

        table.add_column("Symbol", style="bold white", justify="center")
        table.add_column("Price", justify="right")
        table.add_column("Change", justify="right")
        table.add_column("Volume", justify="right")
        table.add_column("Range", justify="center")

        for market in markets:
            change_style = Theme.PROFIT if market.change >= 0 else Theme.LOSS
            change_str = f"{market.change:+.2f} ({market.change_pct:+.2f}%)"

            table.add_row(
                market.symbol,
                f"${market.price:,.2f}",
                Text(change_str, style=change_style),
                f"{market.volume:,}",
                f"${market.low:.2f} - ${market.high:.2f}"
            )

        return Panel(table, border_style=Theme.BORDER)

    @staticmethod
    def create_scanner_panel(alerts: List[ScannerAlert]) -> Panel:
        """Create scanner alerts panel."""
        table = Table(
            title="🔍 Scanner Alerts",
            box=ROUNDED,
            title_style=Theme.SUBHEADER,
            expand=True
        )

        table.add_column("Time", style="dim", width=8)
        table.add_column("Symbol", style="bold")
        table.add_column("Type", justify="center")
        table.add_column("Dir", justify="center")
        table.add_column("Conf", justify="right")
        table.add_column("Price", justify="right")
        table.add_column("Pri", justify="center")

        priority_styles = {
            'CRITICAL': Theme.CRITICAL,
            'HIGH': Theme.HIGH,
            'MEDIUM': Theme.MEDIUM,
            'LOW': Theme.LOW
        }

        direction_styles = {
            'CALL': Theme.BULLISH,
            'PUT': Theme.BEARISH,
            'BUY': Theme.BULLISH,
            'SELL': Theme.BEARISH
        }

        for alert in alerts[:10]:  # Show top 10
            pri_style = priority_styles.get(alert.priority.upper(), Theme.MEDIUM)
            dir_style = direction_styles.get(alert.direction.upper(), Theme.NEUTRAL)

            table.add_row(
                alert.timestamp.strftime("%H:%M:%S"),
                alert.symbol,
                alert.alert_type,
                Text(alert.direction, style=dir_style),
                f"{alert.confidence:.0f}%",
                f"${alert.price:.2f}",
                Text(alert.priority[:3], style=pri_style)
            )

        return Panel(table, border_style=Theme.BORDER)

    @staticmethod
    def create_positions_panel(positions: List[Position]) -> Panel:
        """Create positions panel."""
        table = Table(
            title="📈 Open Positions",
            box=ROUNDED,
            title_style=Theme.SUBHEADER,
            expand=True
        )

        table.add_column("Symbol", style="bold")
        table.add_column("Dir", justify="center")
        table.add_column("Qty", justify="right")
        table.add_column("Entry", justify="right")
        table.add_column("Current", justify="right")
        table.add_column("P&L", justify="right")
        table.add_column("P&L %", justify="right")

        total_pnl = 0
        for pos in positions:
            pnl_style = Theme.PROFIT if pos.pnl >= 0 else Theme.LOSS
            total_pnl += pos.pnl

            table.add_row(
                pos.symbol,
                Text(pos.direction, style=Theme.BULLISH if pos.direction == "LONG" else Theme.BEARISH),
                str(pos.quantity),
                f"${pos.entry_price:.2f}",
                f"${pos.current_price:.2f}",
                Text(f"${pos.pnl:+,.2f}", style=pnl_style),
                Text(f"{pos.pnl_pct:+.2f}%", style=pnl_style)
            )

        # Add total row
        total_style = Theme.PROFIT if total_pnl >= 0 else Theme.LOSS
        table.add_row(
            Text("TOTAL", style="bold"),
            "", "", "", "",
            Text(f"${total_pnl:+,.2f}", style=f"bold {total_style}"),
            ""
        )

        return Panel(table, border_style=Theme.BORDER)

    @staticmethod
    def create_performance_panel(stats: Dict[str, Any]) -> Panel:
        """Create performance metrics panel."""
        table = Table(
            title="📊 Performance Metrics",
            box=ROUNDED,
            title_style=Theme.SUBHEADER,
            show_header=False,
            expand=True
        )

        table.add_column("Metric", style="bold")
        table.add_column("Value", justify="right")

        metrics = [
            ("Total Trades", stats.get("total_trades", 0)),
            ("Win Rate", stats.get("win_rate", "0%")),
            ("Total P&L", stats.get("total_pnl", "$0")),
            ("Profit Factor", stats.get("profit_factor", "0")),
            ("Avg Win", stats.get("avg_win", "$0")),
            ("Avg Loss", stats.get("avg_loss", "$0")),
            ("Sharpe Ratio", stats.get("sharpe", "0")),
            ("Max Drawdown", stats.get("max_dd", "0%"))
        ]

        for metric, value in metrics:
            table.add_row(metric, str(value))

        return Panel(table, border_style=Theme.BORDER)

    @staticmethod
    def create_flow_panel(flow_data: Dict[str, Any]) -> Panel:
        """Create options flow panel."""
        content = Text()

        sentiment = flow_data.get("sentiment", "neutral").upper()
        sentiment_style = {
            "BULLISH": Theme.BULLISH,
            "BEARISH": Theme.BEARISH,
            "NEUTRAL": Theme.NEUTRAL
        }.get(sentiment, Theme.NEUTRAL)

        content.append("Sentiment: ", style="bold")
        content.append(f"{sentiment}\n", style=sentiment_style)

        content.append("Put/Call Ratio: ", style="bold")
        pcr = flow_data.get("put_call_ratio", 1.0)
        pcr_style = Theme.BULLISH if pcr < 0.8 else Theme.BEARISH if pcr > 1.2 else Theme.NEUTRAL
        content.append(f"{pcr:.2f}\n", style=pcr_style)

        content.append("Call Premium: ", style="bold")
        content.append(f"${flow_data.get('call_premium', 0):,.0f}\n")

        content.append("Put Premium: ", style="bold")
        content.append(f"${flow_data.get('put_premium', 0):,.0f}\n")

        content.append("Sweeps: ", style="bold")
        content.append(f"{flow_data.get('sweep_count', 0)}\n")

        smart_money = flow_data.get("smart_money", "neutral").upper()
        content.append("Smart Money: ", style="bold")
        sm_style = Theme.BULLISH if smart_money == "BULLISH" else Theme.BEARISH if smart_money == "BEARISH" else Theme.NEUTRAL
        content.append(f"{smart_money}", style=sm_style)

        return Panel(
            content,
            title="💰 Options Flow",
            title_align="left",
            border_style=Theme.BORDER
        )

    @staticmethod
    def create_greeks_panel(greeks: Dict[str, float]) -> Panel:
        """Create Greeks exposure panel."""
        table = Table(
            title="📐 Portfolio Greeks",
            box=ROUNDED,
            title_style=Theme.SUBHEADER,
            show_header=False,
            expand=True
        )

        table.add_column("Greek", style="bold")
        table.add_column("Value", justify="right")
        table.add_column("Status", justify="center")

        greek_limits = {
            "Delta": (greeks.get("delta", 0), 100),
            "Gamma": (greeks.get("gamma", 0), 50),
            "Theta": (greeks.get("theta", 0), -500),
            "Vega": (greeks.get("vega", 0), 1000),
        }

        for greek, (value, limit) in greek_limits.items():
            pct_of_limit = abs(value / limit) * 100 if limit != 0 else 0

            if pct_of_limit > 80:
                status = Text("⚠️ HIGH", style=Theme.WARNING)
            elif pct_of_limit > 50:
                status = Text("● OK", style=Theme.NEUTRAL)
            else:
                status = Text("✓ LOW", style=Theme.SUCCESS)

            table.add_row(greek, f"{value:+,.2f}", status)

        return Panel(table, border_style=Theme.BORDER)

    @staticmethod
    def create_system_status(status: Dict[str, Any]) -> Panel:
        """Create system status panel."""
        content = Text()

        # Connection status
        content.append("Connections:\n", style="bold")
        connections = status.get("connections", {})
        for name, is_connected in connections.items():
            icon = "✓" if is_connected else "✗"
            style = Theme.SUCCESS if is_connected else Theme.ERROR
            content.append(f"  {icon} {name}\n", style=style)

        content.append("\n")

        # Scanner status
        content.append("Scanners:\n", style="bold")
        scanners = status.get("scanners", {})
        for name, is_running in scanners.items():
            icon = "●" if is_running else "○"
            style = Theme.SUCCESS if is_running else Theme.LOW
            content.append(f"  {icon} {name}\n", style=style)

        content.append("\n")

        # Resource usage
        content.append("Resources:\n", style="bold")
        content.append(f"  CPU: {status.get('cpu_pct', 0):.1f}%\n")
        content.append(f"  Memory: {status.get('memory_pct', 0):.1f}%\n")
        content.append(f"  Latency: {status.get('latency_ms', 0):.0f}ms\n")

        return Panel(
            content,
            title="⚙️ System Status",
            title_align="left",
            border_style=Theme.BORDER
        )


class RevolutionDashboard:
    """
    Main dashboard class.

    Usage:
        dashboard = RevolutionDashboard()
        dashboard.start()
    """

    def __init__(self):
        self.console = Console()
        self.components = DashboardComponents()
        self.running = False

        # Data stores
        self.market_data: List[MarketData] = []
        self.scanner_alerts: List[ScannerAlert] = []
        self.positions: List[Position] = []
        self.performance_stats: Dict[str, Any] = {}
        self.flow_data: Dict[str, Any] = {}
        self.greeks: Dict[str, float] = {}
        self.system_status: Dict[str, Any] = {}

    def create_layout(self) -> Layout:
        """Create the dashboard layout."""
        layout = Layout()

        # Main structure
        layout.split_column(
            Layout(name="header", size=6),
            Layout(name="status_bar", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3)
        )

        # Body split
        layout["body"].split_row(
            Layout(name="left", ratio=2),
            Layout(name="right", ratio=1)
        )

        # Left panel split
        layout["left"].split_column(
            Layout(name="market"),
            Layout(name="scanner"),
            Layout(name="positions")
        )

        # Right panel split
        layout["right"].split_column(
            Layout(name="performance"),
            Layout(name="flow"),
            Layout(name="greeks"),
            Layout(name="system")
        )

        return layout

    def update_layout(self, layout: Layout) -> None:
        """Update layout with current data."""
        # Header
        layout["header"].update(self.components.create_header())

        # Status bar
        layout["status_bar"].update(
            self.components.create_status_bar(
                status="RUNNING" if self.running else "STOPPED",
                mode="LIVE"
            )
        )

        # Market overview
        layout["market"].update(self.components.create_market_overview(self.market_data))

        # Scanner alerts
        layout["scanner"].update(self.components.create_scanner_panel(self.scanner_alerts))

        # Positions
        layout["positions"].update(self.components.create_positions_panel(self.positions))

        # Performance
        layout["performance"].update(self.components.create_performance_panel(self.performance_stats))

        # Flow
        layout["flow"].update(self.components.create_flow_panel(self.flow_data))

        # Greeks
        layout["greeks"].update(self.components.create_greeks_panel(self.greeks))

        # System status
        layout["system"].update(self.components.create_system_status(self.system_status))

        # Footer
        layout["footer"].update(Panel(
            Text("Press Ctrl+C to exit | [H]elp | [R]efresh | [S]ettings", justify="center"),
            box=box.SIMPLE
        ))

    def update_data(
        self,
        market_data: Optional[List[MarketData]] = None,
        scanner_alerts: Optional[List[ScannerAlert]] = None,
        positions: Optional[List[Position]] = None,
        performance_stats: Optional[Dict[str, Any]] = None,
        flow_data: Optional[Dict[str, Any]] = None,
        greeks: Optional[Dict[str, float]] = None,
        system_status: Optional[Dict[str, Any]] = None
    ) -> None:
        """Update dashboard data."""
        if market_data is not None:
            self.market_data = market_data
        if scanner_alerts is not None:
            self.scanner_alerts = scanner_alerts
        if positions is not None:
            self.positions = positions
        if performance_stats is not None:
            self.performance_stats = performance_stats
        if flow_data is not None:
            self.flow_data = flow_data
        if greeks is not None:
            self.greeks = greeks
        if system_status is not None:
            self.system_status = system_status

    def start(self, refresh_rate: float = 1.0) -> None:
        """Start the live dashboard."""
        self.running = True
        layout = self.create_layout()

        with Live(layout, console=self.console, refresh_per_second=1/refresh_rate) as live:
            try:
                while self.running:
                    self.update_layout(layout)
                    time.sleep(refresh_rate)
            except KeyboardInterrupt:
                self.running = False

    def stop(self) -> None:
        """Stop the dashboard."""
        self.running = False

    def render_once(self) -> None:
        """Render dashboard once (for testing)."""
        layout = self.create_layout()
        self.update_layout(layout)
        self.console.print(layout)


def create_demo_dashboard() -> RevolutionDashboard:
    """Create a dashboard with demo data."""
    dashboard = RevolutionDashboard()

    # Demo market data
    dashboard.market_data = [
        MarketData("SPX", 4532.50, 15.30, 0.34, 2500000000, 4545.00, 4510.00),
        MarketData("SPY", 452.80, 1.50, 0.33, 85000000, 454.00, 451.00),
        MarketData("QQQ", 385.20, -2.10, -0.54, 45000000, 388.00, 383.00),
        MarketData("VIX", 14.50, -0.80, -5.23, 0, 15.50, 14.20),
    ]

    # Demo alerts
    dashboard.scanner_alerts = [
        ScannerAlert(datetime.now(), "SPX", "MOMENTUM", "CALL", 85.5, 4.50, "HIGH"),
        ScannerAlert(datetime.now(), "AAPL", "FLOW", "CALL", 78.0, 2.30, "MEDIUM"),
        ScannerAlert(datetime.now(), "TSLA", "SQUEEZE", "PUT", 92.0, 8.20, "CRITICAL"),
    ]

    # Demo positions
    dashboard.positions = [
        Position("SPX 4530C", "LONG", 5, 4.50, 5.20, 350, 15.6),
        Position("QQQ 385P", "LONG", 10, 2.00, 1.80, -200, -10.0),
    ]

    # Demo stats
    dashboard.performance_stats = {
        "total_trades": 156,
        "win_rate": "68.5%",
        "total_pnl": "$12,450",
        "profit_factor": "2.35",
        "avg_win": "$285",
        "avg_loss": "$125",
        "sharpe": "1.85",
        "max_dd": "8.5%"
    }

    # Demo flow
    dashboard.flow_data = {
        "sentiment": "bullish",
        "put_call_ratio": 0.72,
        "call_premium": 15000000,
        "put_premium": 8500000,
        "sweep_count": 23,
        "smart_money": "bullish"
    }

    # Demo Greeks
    dashboard.greeks = {
        "delta": 45.5,
        "gamma": 12.3,
        "theta": -125.0,
        "vega": 450.0
    }

    # Demo system status
    dashboard.system_status = {
        "connections": {
            "Data Feed": True,
            "Broker": True,
            "Database": True
        },
        "scanners": {
            "Momentum": True,
            "Options Flow": True,
            "Squeeze": True,
            "MTF": False
        },
        "cpu_pct": 23.5,
        "memory_pct": 45.2,
        "latency_ms": 12
    }

    return dashboard


if __name__ == "__main__":
    # Demo run
    dashboard = create_demo_dashboard()
    dashboard.render_once()
