"""
Enhanced Visual Dashboard.

State-of-the-art terminal UI with:
- Real-time ASCII charts and sparklines
- Color-coded signal displays
- Interactive menus
- Live updating panels
- Gradient color schemes
- Animated elements
- Multi-panel layouts
"""

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.layout import Layout
from rich.live import Live
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
from rich.style import Style
from rich.align import Align
from rich.columns import Columns
from rich.box import DOUBLE, ROUNDED, HEAVY, MINIMAL
from rich.tree import Tree
from rich.syntax import Syntax
from rich.markdown import Markdown
import numpy as np
from typing import Dict, List, Optional, Tuple, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import asyncio
import time


class ColorScheme(Enum):
    """Dashboard color schemes."""
    CYBERPUNK = "cyberpunk"
    MATRIX = "matrix"
    OCEAN = "ocean"
    SUNSET = "sunset"
    PROFESSIONAL = "professional"


@dataclass
class ChartConfig:
    """Configuration for ASCII charts."""
    width: int = 60
    height: int = 10
    show_labels: bool = True
    show_grid: bool = True
    style: str = "line"  # line, bar, candle, area


class ASCIIChart:
    """
    Create beautiful ASCII charts for terminal display.
    """

    # Unicode characters for drawing
    BLOCKS = " ▁▂▃▄▅▆▇█"
    BRAILLE = "⠀⠁⠂⠃⠄⠅⠆⠇⡀⡁⡂⡃⡄⡅⡆⡇⠈⠉⠊⠋⠌⠍⠎⠏⡈⡉⡊⡋⡌⡍⡎⡏⠐⠑⠒⠓⠔⠕⠖⠗⡐⡑⡒⡓⡔⡕⡖⡗⠘⠙⠚⠛⠜⠝⠞⠟⡘⡙⡚⡛⡜⡝⡞⡟⠠⠡⠢⠣⠤⠥⠦⠧⡠⡡⡢⡣⡤⡥⡦⡧⠨⠩⠪⠫⠬⠭⠮⠯⡨⡩⡪⡫⡬⡭⡮⡯⠰⠱⠲⠳⠴⠵⠶⠷⡰⡱⡲⡳⡴⡵⡶⡷⠸⠹⠺⠻⠼⠽⠾⠿⡸⡹⡺⡻⡼⡽⡾⡿⢀⢁⢂⢃⢄⢅⢆⢇⣀⣁⣂⣃⣄⣅⣆⣇⢈⢉⢊⢋⢌⢍⢎⢏⣈⣉⣊⣋⣌⣍⣎⣏⢐⢑⢒⢓⢔⢕⢖⢗⣐⣑⣒⣓⣔⣕⣖⣗⢘⢙⢚⢛⢜⢝⢞⢟⣘⣙⣚⣛⣜⣝⣞⣟⢠⢡⢢⢣⢤⢥⢦⢧⣠⣡⣢⣣⣤⣥⣦⣧⢨⢩⢪⢫⢬⢭⢮⢯⣨⣩⣪⣫⣬⣭⣮⣯⢰⢱⢲⢳⢴⢵⢶⢷⣰⣱⣲⣳⣴⣵⣶⣷⢸⢹⢺⢻⢼⢽⢾⢿⣸⣹⣺⣻⣼⣽⣾⣿"
    LINE_CHARS = "─│┌┐└┘├┤┬┴┼╭╮╯╰"

    def __init__(self, config: Optional[ChartConfig] = None):
        self.config = config or ChartConfig()

    def sparkline(
        self,
        data: List[float],
        width: Optional[int] = None,
        color: str = "green",
    ) -> Text:
        """Create a sparkline chart."""
        if not data:
            return Text("No data")

        width = width or min(len(data), self.config.width)
        data = self._resample(data, width)

        min_val = min(data)
        max_val = max(data)
        range_val = max_val - min_val or 1

        chars = []
        for val in data:
            idx = int((val - min_val) / range_val * (len(self.BLOCKS) - 1))
            chars.append(self.BLOCKS[idx])

        text = Text("".join(chars))
        text.stylize(color)

        return text

    def line_chart(
        self,
        data: List[float],
        width: Optional[int] = None,
        height: Optional[int] = None,
        title: str = "",
        color: str = "cyan",
        show_values: bool = True,
    ) -> str:
        """Create a line chart with axes."""
        if not data:
            return "No data"

        width = width or self.config.width
        height = height or self.config.height

        data = self._resample(data, width)

        min_val = min(data)
        max_val = max(data)
        range_val = max_val - min_val or 1

        # Create canvas
        canvas = [[" " for _ in range(width + 8)] for _ in range(height + 2)]

        # Draw Y axis labels
        for i in range(height):
            y_val = max_val - (i / (height - 1)) * range_val
            label = f"{y_val:>6.2f} │"
            for j, char in enumerate(label):
                canvas[i][j] = char

        # Draw X axis
        canvas[height] = list("       └" + "─" * width)

        # Plot data points
        for x, val in enumerate(data):
            y = int((max_val - val) / range_val * (height - 1))
            y = max(0, min(height - 1, y))
            canvas[y][x + 8] = "●"

            # Connect points with lines
            if x > 0:
                prev_y = int((max_val - data[x - 1]) / range_val * (height - 1))
                prev_y = max(0, min(height - 1, prev_y))

                if prev_y != y:
                    step = 1 if y > prev_y else -1
                    for yi in range(prev_y, y, step):
                        if canvas[yi][x + 7] == " ":
                            canvas[yi][x + 7] = "│"

        # Add title
        if title:
            title_line = f"  {title}  ".center(width + 8)
            canvas.insert(0, list(title_line))

        return "\n".join("".join(row) for row in canvas)

    def bar_chart(
        self,
        data: Dict[str, float],
        width: int = 40,
        show_values: bool = True,
    ) -> str:
        """Create a horizontal bar chart."""
        if not data:
            return "No data"

        max_val = max(data.values())
        max_label_len = max(len(k) for k in data.keys())

        lines = []

        for label, value in data.items():
            bar_width = int((value / max_val) * (width - max_label_len - 10))
            bar = "█" * bar_width

            # Color based on value
            if value >= max_val * 0.8:
                color = "green"
            elif value >= max_val * 0.5:
                color = "yellow"
            else:
                color = "red"

            if show_values:
                line = f"{label:<{max_label_len}} │ [{color}]{bar}[/] {value:.2f}"
            else:
                line = f"{label:<{max_label_len}} │ [{color}]{bar}[/]"

            lines.append(line)

        return "\n".join(lines)

    def candlestick(
        self,
        ohlc: List[Tuple[float, float, float, float]],
        width: Optional[int] = None,
    ) -> str:
        """Create ASCII candlestick chart."""
        if not ohlc:
            return "No data"

        width = width or min(len(ohlc), self.config.width)

        # Resample if needed
        step = max(1, len(ohlc) // width)
        sampled = ohlc[::step][:width]

        all_prices = [p for candle in sampled for p in candle]
        min_val = min(all_prices)
        max_val = max(all_prices)
        range_val = max_val - min_val or 1

        height = self.config.height

        # Create canvas
        canvas = [[" " for _ in range(len(sampled))] for _ in range(height)]

        for x, (o, h, l, c) in enumerate(sampled):
            # Scale prices to canvas
            o_y = int((1 - (o - min_val) / range_val) * (height - 1))
            h_y = int((1 - (h - min_val) / range_val) * (height - 1))
            l_y = int((1 - (l - min_val) / range_val) * (height - 1))
            c_y = int((1 - (c - min_val) / range_val) * (height - 1))

            # Draw wick
            for y in range(h_y, l_y + 1):
                canvas[y][x] = "│"

            # Draw body
            body_top = min(o_y, c_y)
            body_bot = max(o_y, c_y)
            body_char = "█" if c >= o else "░"

            for y in range(body_top, body_bot + 1):
                canvas[y][x] = body_char

        return "\n".join("".join(row) for row in canvas)

    def heatmap(
        self,
        data: List[List[float]],
        row_labels: Optional[List[str]] = None,
        col_labels: Optional[List[str]] = None,
    ) -> str:
        """Create a heatmap using colored blocks."""
        if not data:
            return "No data"

        # Normalize data
        flat = [v for row in data for v in row]
        min_val = min(flat)
        max_val = max(flat)
        range_val = max_val - min_val or 1

        # Color gradient
        colors = [
            (0.0, "blue"),
            (0.25, "cyan"),
            (0.5, "green"),
            (0.75, "yellow"),
            (1.0, "red"),
        ]

        lines = []

        # Column labels
        if col_labels:
            header = "     " + " ".join(f"{l:>4}" for l in col_labels[:10])
            lines.append(header)

        for i, row in enumerate(data):
            cells = []
            for val in row:
                norm = (val - min_val) / range_val

                # Find color
                color = "white"
                for threshold, c in colors:
                    if norm >= threshold:
                        color = c

                cells.append(f"[{color}]██[/]")

            row_label = row_labels[i] if row_labels and i < len(row_labels) else f"{i:>3}"
            lines.append(f"{row_label} │ " + " ".join(cells))

        return "\n".join(lines)

    def _resample(self, data: List[float], target_len: int) -> List[float]:
        """Resample data to target length."""
        if len(data) <= target_len:
            return data

        step = len(data) / target_len
        return [data[int(i * step)] for i in range(target_len)]


class SignalPanel:
    """
    Panel for displaying trading signals.
    """

    def __init__(self, console: Console):
        self.console = console
        self.chart = ASCIIChart()

    def create(
        self,
        signals: List[Dict[str, Any]],
        title: str = "📡 LIVE SIGNALS",
    ) -> Panel:
        """Create signal display panel."""
        table = Table(
            show_header=True,
            header_style="bold magenta",
            box=ROUNDED,
            expand=True,
        )

        table.add_column("Symbol", style="cyan", width=8)
        table.add_column("Signal", width=10)
        table.add_column("Strength", width=10)
        table.add_column("Price", width=12)
        table.add_column("Trend", width=15)
        table.add_column("Confidence", width=12)

        for signal in signals[:10]:
            # Signal indicator
            direction = signal.get("direction", 0)
            if direction > 0:
                signal_text = Text("▲ LONG", style="bold green")
            elif direction < 0:
                signal_text = Text("▼ SHORT", style="bold red")
            else:
                signal_text = Text("● HOLD", style="yellow")

            # Strength bar
            strength = signal.get("strength", 0.5)
            strength_bar = "█" * int(strength * 10)
            strength_color = "green" if strength > 0.7 else "yellow" if strength > 0.4 else "red"
            strength_text = Text(strength_bar, style=strength_color)

            # Sparkline for recent prices
            prices = signal.get("recent_prices", [])
            if prices:
                trend = self.chart.sparkline(prices, width=12, color="cyan")
            else:
                trend = Text("─" * 12, style="dim")

            # Confidence bar
            confidence = signal.get("confidence", 0.5)
            conf_filled = "●" * int(confidence * 5)
            conf_empty = "○" * (5 - int(confidence * 5))
            conf_text = Text(conf_filled + conf_empty, style="magenta")

            table.add_row(
                signal.get("symbol", "---"),
                signal_text,
                strength_text,
                f"${signal.get('price', 0):,.2f}",
                trend,
                conf_text,
            )

        return Panel(
            table,
            title=f"[bold cyan]{title}[/]",
            border_style="cyan",
            box=DOUBLE,
        )


class PerformancePanel:
    """
    Panel for displaying performance metrics.
    """

    def __init__(self):
        self.chart = ASCIIChart()

    def create(
        self,
        metrics: Dict[str, Any],
        equity_curve: List[float],
        title: str = "📈 PERFORMANCE",
    ) -> Panel:
        """Create performance panel with chart."""
        content = []

        # Key metrics in columns
        metrics_table = Table(show_header=False, box=None, expand=True)
        metrics_table.add_column("Metric", width=20)
        metrics_table.add_column("Value", width=15)
        metrics_table.add_column("Metric", width=20)
        metrics_table.add_column("Value", width=15)

        # Row 1
        total_return = metrics.get("total_return", 0)
        return_color = "green" if total_return >= 0 else "red"
        sharpe = metrics.get("sharpe", 0)

        metrics_table.add_row(
            "Total Return",
            Text(f"{total_return:+.2%}", style=return_color),
            "Sharpe Ratio",
            Text(f"{sharpe:.2f}", style="cyan"),
        )

        # Row 2
        max_dd = metrics.get("max_drawdown", 0)
        win_rate = metrics.get("win_rate", 0)

        metrics_table.add_row(
            "Max Drawdown",
            Text(f"{max_dd:.2%}", style="red"),
            "Win Rate",
            Text(f"{win_rate:.1%}", style="green" if win_rate > 0.5 else "yellow"),
        )

        # Row 3
        trades = metrics.get("total_trades", 0)
        profit_factor = metrics.get("profit_factor", 0)

        metrics_table.add_row(
            "Total Trades",
            Text(f"{trades}", style="white"),
            "Profit Factor",
            Text(f"{profit_factor:.2f}", style="green" if profit_factor > 1 else "red"),
        )

        content.append(metrics_table)
        content.append(Text("\n"))

        # Equity curve sparkline
        if equity_curve:
            content.append(Text("Equity Curve:", style="bold"))
            sparkline = self.chart.sparkline(
                equity_curve,
                width=60,
                color="green" if equity_curve[-1] > equity_curve[0] else "red"
            )
            content.append(sparkline)

        return Panel(
            Group(*content),
            title=f"[bold green]{title}[/]",
            border_style="green",
            box=DOUBLE,
        )


class RiskPanel:
    """
    Panel for displaying risk metrics.
    """

    def __init__(self):
        self.chart = ASCIIChart()

    def create(
        self,
        risk_metrics: Dict[str, Any],
        title: str = "⚠️  RISK MONITOR",
    ) -> Panel:
        """Create risk monitoring panel."""
        content = []

        # Risk level indicator
        risk_level = risk_metrics.get("overall_risk", 0.5)

        if risk_level < 0.3:
            risk_text = "🟢 LOW RISK"
            risk_style = "green"
        elif risk_level < 0.6:
            risk_text = "🟡 MODERATE"
            risk_style = "yellow"
        elif risk_level < 0.8:
            risk_text = "🟠 ELEVATED"
            risk_style = "rgb(255,165,0)"
        else:
            risk_text = "🔴 HIGH RISK"
            risk_style = "red bold"

        content.append(Align.center(Text(risk_text, style=risk_style)))
        content.append(Text("\n"))

        # Risk bar
        risk_bar_filled = "█" * int(risk_level * 30)
        risk_bar_empty = "░" * (30 - int(risk_level * 30))
        risk_bar = Text()
        risk_bar.append(risk_bar_filled, style=risk_style)
        risk_bar.append(risk_bar_empty, style="dim")
        content.append(Align.center(risk_bar))
        content.append(Text("\n"))

        # Individual risk metrics
        risk_table = Table(show_header=True, box=MINIMAL, expand=True)
        risk_table.add_column("Risk Factor", style="cyan")
        risk_table.add_column("Value", justify="right")
        risk_table.add_column("Status", justify="center")

        risk_items = [
            ("VaR (95%)", risk_metrics.get("var_95", 0), 0.02),
            ("CVaR (95%)", risk_metrics.get("cvar_95", 0), 0.03),
            ("Position Size", risk_metrics.get("position_size", 0), 0.1),
            ("Correlation Risk", risk_metrics.get("correlation_risk", 0), 0.5),
            ("Liquidity Risk", risk_metrics.get("liquidity_risk", 0), 0.3),
            ("Volatility", risk_metrics.get("volatility", 0), 0.02),
        ]

        for name, value, threshold in risk_items:
            if isinstance(value, float) and value < 1:
                value_str = f"{value:.2%}"
            else:
                value_str = f"{value:.2f}"

            if value < threshold * 0.5:
                status = "🟢"
            elif value < threshold:
                status = "🟡"
            else:
                status = "🔴"

            risk_table.add_row(name, value_str, status)

        content.append(risk_table)

        return Panel(
            Group(*content),
            title=f"[bold yellow]{title}[/]",
            border_style="yellow",
            box=DOUBLE,
        )


class OrderBookPanel:
    """
    Visual order book display.
    """

    def create(
        self,
        bids: List[Tuple[float, int]],
        asks: List[Tuple[float, int]],
        title: str = "📊 ORDER BOOK",
    ) -> Panel:
        """Create order book visualization."""
        table = Table(show_header=True, box=ROUNDED, expand=True)

        table.add_column("Bid Size", justify="right", style="green")
        table.add_column("Bid", justify="right", style="green bold")
        table.add_column("Ask", justify="left", style="red bold")
        table.add_column("Ask Size", justify="left", style="red")

        max_size = max(
            [s for _, s in bids[:10]] + [s for _, s in asks[:10]],
            default=1
        )

        for i in range(min(10, max(len(bids), len(asks)))):
            bid_price = bids[i][0] if i < len(bids) else 0
            bid_size = bids[i][1] if i < len(bids) else 0
            ask_price = asks[i][0] if i < len(asks) else 0
            ask_size = asks[i][1] if i < len(asks) else 0

            # Size bars
            bid_bar = "█" * int(bid_size / max_size * 15)
            ask_bar = "█" * int(ask_size / max_size * 15)

            table.add_row(
                f"{bid_bar} {bid_size:,}" if bid_size else "",
                f"${bid_price:,.2f}" if bid_price else "",
                f"${ask_price:,.2f}" if ask_price else "",
                f"{ask_size:,} {ask_bar}" if ask_size else "",
            )

        return Panel(
            table,
            title=f"[bold blue]{title}[/]",
            border_style="blue",
            box=DOUBLE,
        )


class HeaderPanel:
    """
    Header panel with system status.
    """

    def create(
        self,
        status: Dict[str, Any],
    ) -> Panel:
        """Create header panel."""
        # ASCII art logo
        logo = """
╔═══════════════════════════════════════════════════════════════════════════════╗
║  ██████╗ ███████╗██╗   ██╗ ██████╗ ██╗     ██╗   ██╗████████╗██╗ ██████╗ ███╗   ██╗ ║
║  ██╔══██╗██╔════╝██║   ██║██╔═══██╗██║     ██║   ██║╚══██╔══╝██║██╔═══██╗████╗  ██║ ║
║  ██████╔╝█████╗  ██║   ██║██║   ██║██║     ██║   ██║   ██║   ██║██║   ██║██╔██╗ ██║ ║
║  ██╔══██╗██╔══╝  ╚██╗ ██╔╝██║   ██║██║     ██║   ██║   ██║   ██║██║   ██║██║╚██╗██║ ║
║  ██║  ██║███████╗ ╚████╔╝ ╚██████╔╝███████╗╚██████╔╝   ██║   ██║╚██████╔╝██║ ╚████║ ║
║  ╚═╝  ╚═╝╚══════╝  ╚═══╝   ╚═════╝ ╚══════╝ ╚═════╝    ╚═╝   ╚═╝ ╚═════╝ ╚═╝  ╚═══╝ ║
║                           A L P H A   E N G I N E                                    ║
╚═══════════════════════════════════════════════════════════════════════════════╝
"""

        # Status indicators
        status_text = Text()

        # System status
        if status.get("system_ok", True):
            status_text.append("● SYSTEM ONLINE  ", style="green bold")
        else:
            status_text.append("● SYSTEM ERROR  ", style="red bold blink")

        # Market status
        market_status = status.get("market_status", "closed")
        if market_status == "open":
            status_text.append("● MARKET OPEN  ", style="green")
        elif market_status == "pre":
            status_text.append("● PRE-MARKET  ", style="yellow")
        else:
            status_text.append("● MARKET CLOSED  ", style="red")

        # Connection status
        if status.get("connected", True):
            status_text.append("● CONNECTED  ", style="green")
        else:
            status_text.append("● DISCONNECTED  ", style="red blink")

        # Time
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status_text.append(f"│ {now}", style="dim")

        content = Group(
            Text(logo, style="cyan"),
            Align.center(status_text),
        )

        return Panel(
            content,
            border_style="cyan",
            box=HEAVY,
        )


class RevolutionDashboardV2:
    """
    Enhanced Revolution Alpha Engine Dashboard.
    """

    def __init__(
        self,
        refresh_rate: float = 1.0,
        color_scheme: ColorScheme = ColorScheme.CYBERPUNK,
    ):
        self.console = Console()
        self.refresh_rate = refresh_rate
        self.color_scheme = color_scheme

        # Panels
        self.header = HeaderPanel()
        self.signals = SignalPanel(self.console)
        self.performance = PerformancePanel()
        self.risk = RiskPanel()
        self.orderbook = OrderBookPanel()
        self.chart = ASCIIChart()

        # State
        self.is_running = False
        self.data: Dict[str, Any] = {}

    def _create_layout(self) -> Layout:
        """Create dashboard layout."""
        layout = Layout()

        layout.split_column(
            Layout(name="header", size=12),
            Layout(name="main", ratio=3),
            Layout(name="footer", size=3),
        )

        layout["main"].split_row(
            Layout(name="left", ratio=2),
            Layout(name="right", ratio=1),
        )

        layout["left"].split_column(
            Layout(name="signals", ratio=2),
            Layout(name="chart", ratio=1),
        )

        layout["right"].split_column(
            Layout(name="performance"),
            Layout(name="risk"),
        )

        return layout

    def update_data(
        self,
        signals: Optional[List[Dict]] = None,
        metrics: Optional[Dict] = None,
        risk: Optional[Dict] = None,
        equity_curve: Optional[List[float]] = None,
        status: Optional[Dict] = None,
    ):
        """Update dashboard data."""
        if signals:
            self.data["signals"] = signals
        if metrics:
            self.data["metrics"] = metrics
        if risk:
            self.data["risk"] = risk
        if equity_curve:
            self.data["equity_curve"] = equity_curve
        if status:
            self.data["status"] = status

    def _render(self) -> Layout:
        """Render dashboard."""
        layout = self._create_layout()

        # Header
        layout["header"].update(
            self.header.create(self.data.get("status", {}))
        )

        # Signals
        layout["signals"].update(
            self.signals.create(self.data.get("signals", []))
        )

        # Chart
        prices = []
        for signal in self.data.get("signals", []):
            prices.extend(signal.get("recent_prices", []))

        if prices:
            chart_text = self.chart.line_chart(
                prices[-60:],
                width=50,
                height=8,
                title="Price Action",
            )
            layout["chart"].update(
                Panel(chart_text, title="[cyan]📈 CHART[/]", border_style="cyan")
            )
        else:
            layout["chart"].update(
                Panel("Waiting for data...", title="[cyan]📈 CHART[/]")
            )

        # Performance
        layout["performance"].update(
            self.performance.create(
                self.data.get("metrics", {}),
                self.data.get("equity_curve", []),
            )
        )

        # Risk
        layout["risk"].update(
            self.risk.create(self.data.get("risk", {}))
        )

        # Footer
        footer_text = Text()
        footer_text.append(" [Q] Quit  ", style="dim")
        footer_text.append("[R] Refresh  ", style="dim")
        footer_text.append("[S] Settings  ", style="dim")
        footer_text.append("[E] Export  ", style="dim")
        footer_text.append("[H] Help  ", style="dim")

        layout["footer"].update(
            Panel(
                Align.center(footer_text),
                box=MINIMAL,
            )
        )

        return layout

    async def run(self):
        """Run dashboard with live updates."""
        self.is_running = True

        with Live(
            self._render(),
            console=self.console,
            refresh_per_second=1 / self.refresh_rate,
            screen=True,
        ) as live:
            while self.is_running:
                live.update(self._render())
                await asyncio.sleep(self.refresh_rate)

    def stop(self):
        """Stop dashboard."""
        self.is_running = False


def create_dashboard(
    color_scheme: ColorScheme = ColorScheme.CYBERPUNK,
) -> RevolutionDashboardV2:
    """Create enhanced dashboard."""
    return RevolutionDashboardV2(color_scheme=color_scheme)


# Demo function
async def demo_dashboard():
    """Run dashboard demo with sample data."""
    dashboard = create_dashboard()

    # Sample data
    import random

    signals = [
        {
            "symbol": "AAPL",
            "direction": 1,
            "strength": 0.85,
            "price": 178.50,
            "recent_prices": [175 + random.random() * 5 for _ in range(20)],
            "confidence": 0.9,
        },
        {
            "symbol": "TSLA",
            "direction": -1,
            "strength": 0.72,
            "price": 245.30,
            "recent_prices": [250 - random.random() * 10 for _ in range(20)],
            "confidence": 0.75,
        },
        {
            "symbol": "NVDA",
            "direction": 1,
            "strength": 0.95,
            "price": 485.20,
            "recent_prices": [480 + random.random() * 10 for _ in range(20)],
            "confidence": 0.95,
        },
    ]

    metrics = {
        "total_return": 0.156,
        "sharpe": 2.34,
        "max_drawdown": 0.08,
        "win_rate": 0.67,
        "total_trades": 142,
        "profit_factor": 1.85,
    }

    risk = {
        "overall_risk": 0.35,
        "var_95": 0.015,
        "cvar_95": 0.022,
        "position_size": 0.08,
        "correlation_risk": 0.25,
        "liquidity_risk": 0.1,
        "volatility": 0.018,
    }

    equity_curve = [100000]
    for _ in range(100):
        equity_curve.append(equity_curve[-1] * (1 + random.gauss(0.001, 0.01)))

    status = {
        "system_ok": True,
        "market_status": "open",
        "connected": True,
    }

    dashboard.update_data(
        signals=signals,
        metrics=metrics,
        risk=risk,
        equity_curve=equity_curve,
        status=status,
    )

    await dashboard.run()


if __name__ == "__main__":
    asyncio.run(demo_dashboard())
