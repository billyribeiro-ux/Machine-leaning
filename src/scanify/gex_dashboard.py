"""
SCANIFY GEX Dashboard — SpotGamma-Style Gamma Exposure Visualization

Renders a comprehensive GEX profile including:
  - Strike-by-strike gamma exposure bar chart (ASCII)
  - Key levels: Call Wall, Put Wall, Gamma Flip, Max Pain, Vol Trigger
  - Transition Zone boundaries
  - Dealer positioning summary
  - Charm / Vanna / Speed exposure panels
  - GEX momentum and signal alerts
  - Per-strike OI and Greeks detail table

Designed to match the information density and visual style of SpotGamma's
professional GEX displays, rendered in the terminal via the Rich library.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text
from rich.align import Align
from rich.columns import Columns
from rich import box

from .gex_engine import GEXResult, GEXSignal, GEXEngine
from .config import GEXSignalType, SignalDirection
from .data_feeds import OptionsChain, OptionQuote


# ---------------------------------------------------------------------------
# Theme constants
# ---------------------------------------------------------------------------

class GEXTheme:
    POSITIVE_GEX = "green"
    NEGATIVE_GEX = "red"
    CALL_WALL = "bold bright_green"
    PUT_WALL = "bold bright_red"
    GAMMA_FLIP = "bold yellow"
    MAX_PAIN = "bold magenta"
    VOL_TRIGGER = "bold cyan"
    SPOT_PRICE = "bold white on blue"
    TRANSITION_ZONE = "yellow"
    DEALER_LONG = "green"
    DEALER_SHORT = "red"
    CHARM_BULLISH = "green"
    CHARM_BEARISH = "red"
    HEADER = "bold white"
    SUBHEADER = "bold cyan"
    DIM = "dim"
    BORDER = "blue"
    SIGNAL_BULL = "bold green"
    SIGNAL_BEAR = "bold red"
    SIGNAL_NEUTRAL = "bold yellow"
    STRIKE_HIGHLIGHT = "bold white"
    BAR_CALL = "red"
    BAR_PUT = "green"
    NET_POSITIVE = "bright_green"
    NET_NEGATIVE = "bright_red"


# ---------------------------------------------------------------------------
# Data class for dashboard snapshot
# ---------------------------------------------------------------------------

@dataclass
class GEXDashboardData:
    """All data needed to render a single GEX dashboard frame."""
    gex_result: GEXResult
    spot_price: float
    chain: Optional[OptionsChain] = None
    signals: List[GEXSignal] = field(default_factory=list)
    gex_momentum: float = 0.0
    high_speed_strikes: List[float] = field(default_factory=list)
    vix1d: float = 0.0
    vix: float = 0.0
    session_type: str = ""
    time_zone: str = ""


# ---------------------------------------------------------------------------
# Main Dashboard Renderer
# ---------------------------------------------------------------------------

class GEXDashboard:
    """SpotGamma-style GEX visualization for the terminal."""

    # Width of the ASCII bar chart area (characters).
    BAR_WIDTH = 40
    # Maximum strikes to show in the profile (centered on spot).
    MAX_STRIKES_DISPLAY = 30

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()

    # ==================================================================
    # Public API
    # ==================================================================

    def render(self, data: GEXDashboardData) -> None:
        """Render the full GEX dashboard to the console."""
        self.console.clear()
        self.console.print(self._build_header(data))
        self.console.print()
        self.console.print(self._build_key_levels_panel(data))
        self.console.print()
        self.console.print(self._build_gex_profile(data))
        self.console.print()

        columns = Columns([
            self._build_dealer_panel(data),
            self._build_charm_vanna_panel(data),
        ], expand=True, equal=True)
        self.console.print(columns)
        self.console.print()

        if data.signals:
            self.console.print(self._build_signals_panel(data))
            self.console.print()

        self.console.print(self._build_strike_table(data))

    def render_to_string(self, data: GEXDashboardData) -> str:
        """Render dashboard and return as a string (for logging/export)."""
        with self.console.capture() as capture:
            self.render(data)
        return capture.get()

    def render_compact(self, data: GEXDashboardData) -> None:
        """Render a compact single-panel GEX summary (for embedding)."""
        self.console.print(self._build_key_levels_panel(data))
        self.console.print(self._build_gex_profile(data))

    # ==================================================================
    # Header
    # ==================================================================

    def _build_header(self, data: GEXDashboardData) -> Panel:
        header = Text()
        header.append("SCANIFY ", style="bold white")
        header.append("GEX SCANNER", style="bold cyan")
        header.append("  |  ", style="dim")
        header.append("SPX ", style="bold white")
        header.append(f"{data.spot_price:,.2f}", style=GEXTheme.SPOT_PRICE)
        header.append("  |  ", style="dim")

        timestamp = data.gex_result.timestamp.strftime("%H:%M:%S")
        header.append(f"{timestamp} ET", style="dim")

        if data.time_zone:
            header.append("  |  ", style="dim")
            header.append(data.time_zone.replace("_", " ").title(), style="yellow")

        if data.vix1d > 0:
            header.append("  |  ", style="dim")
            header.append("VIX1D ", style="dim")
            vix_style = "green" if data.vix1d < 15 else ("yellow" if data.vix1d < 25 else "red")
            header.append(f"{data.vix1d:.1f}", style=vix_style)

        return Panel(
            Align.center(header),
            box=box.DOUBLE,
            border_style=GEXTheme.BORDER,
        )

    # ==================================================================
    # Key Levels Panel — the core SpotGamma-style level display
    # ==================================================================

    def _build_key_levels_panel(self, data: GEXDashboardData) -> Panel:
        gex = data.gex_result
        spot = data.spot_price

        table = Table(
            box=box.SIMPLE_HEAVY,
            show_header=True,
            header_style=GEXTheme.HEADER,
            expand=True,
            title="KEY GEX LEVELS",
            title_style=GEXTheme.SUBHEADER,
        )

        table.add_column("Level", style="bold", justify="left", min_width=18)
        table.add_column("Strike", justify="center", min_width=10)
        table.add_column("Distance", justify="center", min_width=12)
        table.add_column("GEX ($)", justify="right", min_width=16)
        table.add_column("Role", justify="left", min_width=28)

        levels = self._collect_key_levels(gex, spot)

        for level in levels:
            name, strike, gex_val, role, style = level
            if strike <= 0:
                continue
            dist = strike - spot
            dist_str = f"{dist:+.1f} pts" if dist != 0 else "AT SPOT"
            gex_str = f"{gex_val:,.0f}" if gex_val != 0 else "--"

            table.add_row(
                Text(name, style=style),
                Text(f"{strike:,.0f}", style=style),
                Text(dist_str, style="green" if dist > 0 else ("red" if dist < 0 else "yellow")),
                Text(gex_str, style=GEXTheme.POSITIVE_GEX if gex_val >= 0 else GEXTheme.NEGATIVE_GEX),
                Text(role, style="dim"),
            )

        # Transition zone row
        tz_lo, tz_hi = gex.transition_zone
        if tz_lo > 0 and tz_hi > 0 and tz_lo != tz_hi:
            table.add_row(
                Text("Transition Zone", style=GEXTheme.TRANSITION_ZONE),
                Text(f"{tz_lo:,.0f} - {tz_hi:,.0f}", style=GEXTheme.TRANSITION_ZONE),
                Text(f"{tz_hi - tz_lo:.0f} pts wide", style="dim"),
                Text("--", style="dim"),
                Text("Chop zone: call/put gamma balanced", style="dim"),
            )

        # Spot position relative to key levels
        spot_text = Text()
        if spot > gex.gamma_flip_level > 0:
            spot_text.append("ABOVE gamma flip (positive gamma territory)", style="green")
        elif 0 < spot < gex.gamma_flip_level:
            spot_text.append("BELOW gamma flip (negative gamma territory)", style="red")

        if tz_lo > 0 and tz_hi > 0:
            if tz_lo <= spot <= tz_hi:
                spot_text.append(" | INSIDE transition zone", style="yellow")
            elif spot > tz_hi:
                spot_text.append(" | ABOVE transition zone", style="green")
            elif spot < tz_lo:
                spot_text.append(" | BELOW transition zone", style="red")

        table.add_row(
            Text("SPX SPOT", style=GEXTheme.SPOT_PRICE),
            Text(f"{spot:,.2f}", style=GEXTheme.SPOT_PRICE),
            Text("--", style="dim"),
            Text("--", style="dim"),
            spot_text,
        )

        return Panel(table, border_style=GEXTheme.BORDER)

    def _collect_key_levels(
        self, gex: GEXResult, spot: float
    ) -> List[Tuple[str, float, float, str, str]]:
        """Build sorted list of (name, strike, gex_value, role, style)."""
        levels = []

        if gex.call_wall > 0:
            gex_val = gex.gex_by_strike.get(gex.call_wall, 0)
            levels.append((
                "CALL WALL",
                gex.call_wall,
                gex_val,
                "Resistance — dealers sell to hedge",
                GEXTheme.CALL_WALL,
            ))

        if gex.put_wall > 0:
            gex_val = gex.gex_by_strike.get(gex.put_wall, 0)
            levels.append((
                "PUT WALL",
                gex.put_wall,
                gex_val,
                "Support — dealers buy to hedge",
                GEXTheme.PUT_WALL,
            ))

        if gex.gamma_flip_level > 0:
            levels.append((
                "GAMMA FLIP",
                gex.gamma_flip_level,
                0,
                "Dealer gamma changes sign here",
                GEXTheme.GAMMA_FLIP,
            ))

        if gex.max_pain > 0:
            levels.append((
                "MAX PAIN",
                gex.max_pain,
                gex.gex_by_strike.get(gex.max_pain, 0),
                "Max OI expires worthless — pin magnet",
                GEXTheme.MAX_PAIN,
            ))

        if gex.vol_trigger > 0:
            levels.append((
                "VOL TRIGGER",
                gex.vol_trigger,
                gex.gex_by_strike.get(gex.vol_trigger, 0),
                "Volatility regime boundary",
                GEXTheme.VOL_TRIGGER,
            ))

        if gex.plus_gex_strike > 0:
            gex_val = gex.gex_by_strike.get(gex.plus_gex_strike, 0)
            levels.append((
                "+GEX (Upside Target)",
                gex.plus_gex_strike,
                gex_val,
                "Max positive gamma above spot",
                GEXTheme.POSITIVE_GEX,
            ))

        if gex.minus_gex_strike > 0:
            gex_val = gex.gex_by_strike.get(gex.minus_gex_strike, 0)
            levels.append((
                "-GEX (Downside Target)",
                gex.minus_gex_strike,
                gex_val,
                "Max negative gamma below spot",
                GEXTheme.NEGATIVE_GEX,
            ))

        levels.sort(key=lambda x: x[1], reverse=True)
        return levels

    # ==================================================================
    # GEX Profile — ASCII bar chart of gamma by strike
    # ==================================================================

    def _build_gex_profile(self, data: GEXDashboardData) -> Panel:
        gex = data.gex_result
        spot = data.spot_price

        if not gex.gex_by_strike:
            return Panel(
                Text("No GEX data available", style="dim"),
                title="GEX PROFILE BY STRIKE",
                title_align="left",
                border_style=GEXTheme.BORDER,
            )

        sorted_strikes = sorted(gex.gex_by_strike.keys())

        # Center on spot, limit to MAX_STRIKES_DISPLAY
        nearest_idx = min(
            range(len(sorted_strikes)),
            key=lambda i: abs(sorted_strikes[i] - spot)
        )
        half = self.MAX_STRIKES_DISPLAY // 2
        start = max(0, nearest_idx - half)
        end = min(len(sorted_strikes), start + self.MAX_STRIKES_DISPLAY)
        start = max(0, end - self.MAX_STRIKES_DISPLAY)
        display_strikes = sorted_strikes[start:end]

        # Find max absolute GEX for scaling
        max_abs_gex = max(
            abs(gex.gex_by_strike[k]) for k in display_strikes
        ) if display_strikes else 1.0
        if max_abs_gex == 0:
            max_abs_gex = 1.0

        # Build the bar chart table
        table = Table(
            box=None,
            show_header=True,
            header_style=GEXTheme.HEADER,
            expand=True,
            padding=(0, 0),
        )

        table.add_column("Strike", justify="right", min_width=8, style="bold")
        table.add_column("Call GEX", justify="center", min_width=self.BAR_WIDTH + 2, no_wrap=True)
        table.add_column("Net", justify="center", min_width=3)
        table.add_column("Put GEX", justify="center", min_width=self.BAR_WIDTH + 2, no_wrap=True)
        table.add_column("Net GEX $", justify="right", min_width=14)
        table.add_column("", justify="left", min_width=6)

        for strike in reversed(display_strikes):
            net = gex.gex_by_strike.get(strike, 0)
            call_gex = gex.call_gex_by_strike.get(strike, 0)
            put_gex = gex.put_gex_by_strike.get(strike, 0)

            # Strike label with markers
            strike_text = self._format_strike_label(strike, spot, gex)

            # Call GEX bar (negative = red, extends left from center)
            call_bar = self._make_bar(
                call_gex, max_abs_gex, GEXTheme.BAR_CALL, right_align=True
            )

            # Put GEX bar (positive = green, extends right from center)
            put_bar = self._make_bar(
                put_gex, max_abs_gex, GEXTheme.BAR_PUT, right_align=False
            )

            # Net GEX value
            net_style = GEXTheme.NET_POSITIVE if net >= 0 else GEXTheme.NET_NEGATIVE
            net_str = Text(f"{net:>+13,.0f}", style=net_style)

            # Center marker
            center = Text("|", style="dim")

            # Level markers
            marker = self._get_level_marker(strike, gex)

            table.add_row(strike_text, call_bar, center, put_bar, net_str, marker)

        # Footer with totals
        total_style = GEXTheme.NET_POSITIVE if gex.total_net_gex >= 0 else GEXTheme.NET_NEGATIVE
        footer = Text()
        footer.append(f"Total Net GEX: {gex.total_net_gex:,.0f}", style=total_style)
        footer.append("  |  ", style="dim")
        footer.append(f"Momentum: {data.gex_momentum:+,.0f}/min", style="dim")
        if data.high_speed_strikes:
            footer.append("  |  ", style="dim")
            landmines = ", ".join(f"{s:.0f}" for s in data.high_speed_strikes[:5])
            footer.append(f"Gamma Landmines: {landmines}", style="bold yellow")

        return Panel(
            table,
            title="GEX PROFILE BY STRIKE",
            title_align="left",
            subtitle=footer,
            subtitle_align="left",
            border_style=GEXTheme.BORDER,
        )

    def _format_strike_label(
        self, strike: float, spot: float, gex: GEXResult
    ) -> Text:
        """Format strike with color coding for key levels."""
        label = Text()

        # Determine style based on whether this is a key level
        is_spot = abs(strike - spot) < 2.5
        is_call_wall = abs(strike - gex.call_wall) < 0.01
        is_put_wall = abs(strike - gex.put_wall) < 0.01
        is_max_pain = abs(strike - gex.max_pain) < 0.01
        is_gamma_flip = abs(strike - gex.gamma_flip_level) < 2.5

        if is_spot:
            label.append(f"{strike:>7.0f}", style=GEXTheme.SPOT_PRICE)
        elif is_call_wall:
            label.append(f"{strike:>7.0f}", style=GEXTheme.CALL_WALL)
        elif is_put_wall:
            label.append(f"{strike:>7.0f}", style=GEXTheme.PUT_WALL)
        elif is_max_pain:
            label.append(f"{strike:>7.0f}", style=GEXTheme.MAX_PAIN)
        elif is_gamma_flip:
            label.append(f"{strike:>7.0f}", style=GEXTheme.GAMMA_FLIP)
        elif strike > spot:
            label.append(f"{strike:>7.0f}", style="bright_white")
        else:
            label.append(f"{strike:>7.0f}", style="white")

        return label

    def _make_bar(
        self,
        value: float,
        max_val: float,
        color: str,
        right_align: bool = False,
    ) -> Text:
        """Create an ASCII bar scaled to BAR_WIDTH.

        For call GEX (negative values, right-aligned bars extending left).
        For put GEX (positive values, left-aligned bars extending right).
        """
        if max_val == 0:
            return Text(" " * self.BAR_WIDTH)

        bar_len = int(abs(value) / max_val * self.BAR_WIDTH)
        bar_len = min(bar_len, self.BAR_WIDTH)

        bar_char = "█"  # Full block
        half_char = "░"  # Light shade for partial

        if bar_len == 0:
            return Text(" " * self.BAR_WIDTH)

        bar_str = bar_char * bar_len

        if right_align:
            padded = " " * (self.BAR_WIDTH - bar_len) + bar_str
        else:
            padded = bar_str + " " * (self.BAR_WIDTH - bar_len)

        return Text(padded, style=color)

    def _get_level_marker(self, strike: float, gex: GEXResult) -> Text:
        """Return a short marker for key levels at this strike."""
        markers = []

        if abs(strike - gex.call_wall) < 0.01:
            markers.append(("CW", GEXTheme.CALL_WALL))
        if abs(strike - gex.put_wall) < 0.01:
            markers.append(("PW", GEXTheme.PUT_WALL))
        if abs(strike - gex.gamma_flip_level) < 2.5:
            markers.append(("GF", GEXTheme.GAMMA_FLIP))
        if abs(strike - gex.max_pain) < 0.01:
            markers.append(("MP", GEXTheme.MAX_PAIN))
        if abs(strike - gex.vol_trigger) < 0.01:
            markers.append(("VT", GEXTheme.VOL_TRIGGER))
        if abs(strike - gex.plus_gex_strike) < 0.01:
            markers.append(("+G", GEXTheme.POSITIVE_GEX))
        if abs(strike - gex.minus_gex_strike) < 0.01:
            markers.append(("-G", GEXTheme.NEGATIVE_GEX))

        if not markers:
            return Text("")

        text = Text()
        for i, (m, s) in enumerate(markers):
            if i > 0:
                text.append(" ", style="dim")
            text.append(m, style=s)
        return text

    # ==================================================================
    # Dealer Positioning Panel
    # ==================================================================

    def _build_dealer_panel(self, data: GEXDashboardData) -> Panel:
        gex = data.gex_result

        table = Table(box=None, show_header=False, expand=True, padding=(0, 1))
        table.add_column("Label", style="dim", min_width=20)
        table.add_column("Value", justify="right", min_width=20)

        # Dealer position
        pos_style = GEXTheme.DEALER_LONG if gex.dealer_position == "long_gamma" else GEXTheme.DEALER_SHORT
        pos_label = "LONG GAMMA" if gex.dealer_position == "long_gamma" else "SHORT GAMMA"
        pos_effect = "Dampening (stabilizing)" if gex.dealer_position == "long_gamma" else "Amplifying (destabilizing)"

        table.add_row("Dealer Position", Text(pos_label, style=pos_style))
        table.add_row("Market Effect", Text(pos_effect, style=pos_style))
        table.add_row("", Text(""))

        # Total GEX
        total_style = GEXTheme.NET_POSITIVE if gex.total_net_gex >= 0 else GEXTheme.NET_NEGATIVE
        table.add_row("Total Net GEX", Text(f"${gex.total_net_gex:,.0f}", style=total_style))

        # GEX momentum
        mom_style = "green" if data.gex_momentum > 0 else ("red" if data.gex_momentum < 0 else "dim")
        table.add_row("GEX Momentum", Text(f"{data.gex_momentum:+,.0f}/min", style=mom_style))
        table.add_row("", Text(""))

        # What it means
        table.add_row("", Text(""))
        if gex.dealer_position == "long_gamma":
            table.add_row(
                "Implication",
                Text("Dealers BUY dips, SELL rips", style="dim green")
            )
            table.add_row("", Text("Range-bound likely", style="dim green"))
        else:
            table.add_row(
                "Implication",
                Text("Dealers SELL dips, BUY rips", style="dim red")
            )
            table.add_row("", Text("Breakout/trend likely", style="dim red"))

        return Panel(
            table,
            title="DEALER POSITIONING",
            title_align="left",
            border_style=pos_style,
        )

    # ==================================================================
    # Charm / Vanna / Speed Panel
    # ==================================================================

    def _build_charm_vanna_panel(self, data: GEXDashboardData) -> Panel:
        gex = data.gex_result

        table = Table(box=None, show_header=False, expand=True, padding=(0, 1))
        table.add_column("Greek", style="bold", min_width=20)
        table.add_column("Exposure", justify="right", min_width=20)

        # Charm
        charm_style = GEXTheme.CHARM_BULLISH if gex.net_charm_exposure > 0 else GEXTheme.CHARM_BEARISH
        charm_dir = gex.charm_direction.value.upper()
        table.add_row(
            "Net Charm (ES eq.)",
            Text(f"{gex.net_charm_exposure:+,.0f} contracts", style=charm_style),
        )
        table.add_row(
            "Charm Direction",
            Text(f"{charm_dir}", style=charm_style),
        )

        charm_meaning = (
            "Dealers will BUY futures as day progresses"
            if gex.net_charm_exposure > 0
            else "Dealers will SELL futures as day progresses"
        )
        table.add_row("", Text(charm_meaning, style="dim " + charm_style.replace("bold ", "")))
        table.add_row("", Text(""))

        # Vanna
        vanna_style = "green" if gex.net_vanna_exposure > 0 else "red"
        table.add_row(
            "Net Vanna Exposure",
            Text(f"{gex.net_vanna_exposure:+,.0f}", style=vanna_style),
        )

        if data.vix1d > 0:
            if gex.net_vanna_exposure > 0:
                table.add_row(
                    "If VIX drops",
                    Text("Dealers BUY (supportive)", style="dim green"),
                )
                table.add_row(
                    "If VIX rises",
                    Text("Dealers SELL (destructive)", style="dim red"),
                )
            else:
                table.add_row(
                    "If VIX drops",
                    Text("Dealers SELL", style="dim red"),
                )
                table.add_row(
                    "If VIX rises",
                    Text("Dealers BUY", style="dim green"),
                )

        table.add_row("", Text(""))

        # Speed / Gamma Landmines
        if data.high_speed_strikes:
            landmines = ", ".join(f"{s:.0f}" for s in data.high_speed_strikes[:5])
            table.add_row(
                "Gamma Landmines",
                Text(landmines, style="bold yellow"),
            )
            table.add_row(
                "",
                Text("High speed = gamma accelerates violently", style="dim yellow"),
            )
        else:
            table.add_row("Gamma Landmines", Text("None nearby", style="dim"))

        return Panel(
            table,
            title="CHARM / VANNA / SPEED",
            title_align="left",
            border_style=GEXTheme.BORDER,
        )

    # ==================================================================
    # GEX Signals Panel
    # ==================================================================

    def _build_signals_panel(self, data: GEXDashboardData) -> Panel:
        table = Table(
            box=box.SIMPLE,
            show_header=True,
            header_style=GEXTheme.HEADER,
            expand=True,
        )

        table.add_column("Signal", min_width=24)
        table.add_column("Direction", justify="center", min_width=10)
        table.add_column("Confidence", justify="center", min_width=12)
        table.add_column("Trigger", justify="right", min_width=10)
        table.add_column("Target", justify="right", min_width=10)
        table.add_column("Description", min_width=36)

        for sig in data.signals:
            dir_style = (
                GEXTheme.SIGNAL_BULL if sig.direction == SignalDirection.BULLISH
                else GEXTheme.SIGNAL_BEAR if sig.direction == SignalDirection.BEARISH
                else GEXTheme.SIGNAL_NEUTRAL
            )

            signal_name = sig.signal_type.value.replace("_", " ").title()

            conf_bar = self._confidence_bar(sig.confidence)

            target_str = f"{sig.target_price:,.0f}" if sig.target_price else "--"

            table.add_row(
                Text(signal_name, style="bold"),
                Text(sig.direction.value.upper(), style=dir_style),
                conf_bar,
                Text(f"{sig.trigger_price:,.1f}", style="white"),
                Text(target_str, style="dim"),
                Text(sig.description, style="dim"),
            )

        return Panel(
            table,
            title="ACTIVE GEX SIGNALS",
            title_align="left",
            border_style="yellow",
        )

    def _confidence_bar(self, confidence: float) -> Text:
        """Render a small confidence bar like [========  ] 80%."""
        filled = int(confidence * 10)
        bar = "█" * filled + "░" * (10 - filled)

        if confidence >= 0.7:
            style = "green"
        elif confidence >= 0.5:
            style = "yellow"
        else:
            style = "red"

        text = Text()
        text.append(bar, style=style)
        text.append(f" {confidence:.0%}", style=style)
        return text

    # ==================================================================
    # Detailed Strike Table
    # ==================================================================

    def _build_strike_table(self, data: GEXDashboardData) -> Panel:
        """Per-strike detail table with OI, volume, Greeks, and GEX."""
        gex = data.gex_result
        spot = data.spot_price

        table = Table(
            box=box.SIMPLE_HEAD,
            show_header=True,
            header_style=GEXTheme.HEADER,
            expand=True,
            title="STRIKE DETAIL",
            title_style=GEXTheme.SUBHEADER,
        )

        table.add_column("Strike", justify="right", style="bold", min_width=7)
        table.add_column("Dist", justify="right", min_width=6)
        table.add_column("Call OI", justify="right", min_width=9)
        table.add_column("Put OI", justify="right", min_width=9)
        table.add_column("Call GEX", justify="right", min_width=13)
        table.add_column("Put GEX", justify="right", min_width=13)
        table.add_column("Net GEX", justify="right", min_width=13)
        table.add_column("Speed", justify="right", min_width=10)
        table.add_column("Lvl", justify="center", min_width=6)

        # Get strikes to display, centered on spot
        sorted_strikes = sorted(gex.gex_by_strike.keys())
        if not sorted_strikes:
            return Panel(Text("No strike data", style="dim"), border_style=GEXTheme.BORDER)

        nearest_idx = min(range(len(sorted_strikes)), key=lambda i: abs(sorted_strikes[i] - spot))
        half = self.MAX_STRIKES_DISPLAY // 2
        start = max(0, nearest_idx - half)
        end = min(len(sorted_strikes), start + self.MAX_STRIKES_DISPLAY)
        start = max(0, end - self.MAX_STRIKES_DISPLAY)
        display_strikes = sorted_strikes[start:end]

        # Get OI data from chain if available
        oi_data = {}
        if data.chain:
            for q in data.chain.quotes:
                key = (q.strike, q.option_type)
                oi_data[key] = {
                    "oi": q.open_interest,
                    "volume": q.volume,
                }

        for strike in reversed(display_strikes):
            dist = strike - spot
            dist_str = f"{dist:+.0f}"

            call_oi = oi_data.get((strike, "call"), {}).get("oi", 0)
            put_oi = oi_data.get((strike, "put"), {}).get("oi", 0)

            call_gex = gex.call_gex_by_strike.get(strike, 0)
            put_gex = gex.put_gex_by_strike.get(strike, 0)
            net = gex.gex_by_strike.get(strike, 0)
            speed = gex.net_speed_by_strike.get(strike, 0)

            # Style based on proximity to spot
            is_near_spot = abs(dist) < 5
            strike_style = GEXTheme.SPOT_PRICE if is_near_spot else ""

            call_gex_style = GEXTheme.BAR_CALL if call_gex < 0 else GEXTheme.BAR_PUT
            put_gex_style = GEXTheme.BAR_PUT if put_gex > 0 else GEXTheme.BAR_CALL
            net_style = GEXTheme.NET_POSITIVE if net >= 0 else GEXTheme.NET_NEGATIVE

            marker = self._get_level_marker(strike, gex)

            speed_style = "bold yellow" if abs(speed) > 0 and strike in data.high_speed_strikes else "dim"

            table.add_row(
                Text(f"{strike:,.0f}", style=strike_style),
                Text(dist_str, style="green" if dist > 0 else "red"),
                Text(f"{call_oi:,}", style="dim" if call_oi == 0 else "white"),
                Text(f"{put_oi:,}", style="dim" if put_oi == 0 else "white"),
                Text(f"{call_gex:>+12,.0f}", style=call_gex_style),
                Text(f"{put_gex:>+12,.0f}", style=put_gex_style),
                Text(f"{net:>+12,.0f}", style=net_style),
                Text(f"{speed:>+9,.0f}", style=speed_style),
                marker,
            )

        return Panel(table, border_style=GEXTheme.BORDER)


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

def render_gex_dashboard(
    gex_result: GEXResult,
    spot_price: float,
    chain: Optional[OptionsChain] = None,
    signals: Optional[List[GEXSignal]] = None,
    gex_momentum: float = 0.0,
    high_speed_strikes: Optional[List[float]] = None,
    vix1d: float = 0.0,
    vix: float = 0.0,
    session_type: str = "",
    time_zone: str = "",
    console: Optional[Console] = None,
) -> None:
    """One-call convenience to render the full GEX dashboard."""
    data = GEXDashboardData(
        gex_result=gex_result,
        spot_price=spot_price,
        chain=chain,
        signals=signals or [],
        gex_momentum=gex_momentum,
        high_speed_strikes=high_speed_strikes or [],
        vix1d=vix1d,
        vix=vix,
        session_type=session_type,
        time_zone=time_zone,
    )
    dashboard = GEXDashboard(console=console)
    dashboard.render(data)
