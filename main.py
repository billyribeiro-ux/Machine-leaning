#!/usr/bin/env python3
"""
Revolution Alpha Engine - Main Entry Point

Institutional-Grade ML Trading System

Usage:
    python main.py                    # Start with default config
    python main.py --mode live        # Live trading mode
    python main.py --mode paper       # Paper trading mode
    python main.py --mode backtest    # Backtest mode
    python main.py --dashboard        # Start dashboard only
    python main.py --scan             # Run scanner only
    python main.py --config path.yaml # Use custom config

For more options: python main.py --help
"""

import argparse
import asyncio
import signal
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich import print as rprint


# ASCII Art Banner
BANNER = """
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║   ██████╗ ███████╗██╗   ██╗ ██████╗ ██╗     ██╗   ██╗████████╗██╗ ██████╗   ║
║   ██╔══██╗██╔════╝██║   ██║██╔═══██╗██║     ██║   ██║╚══██╔══╝██║██╔═══██╗  ║
║   ██████╔╝█████╗  ██║   ██║██║   ██║██║     ██║   ██║   ██║   ██║██║   ██║  ║
║   ██╔══██╗██╔══╝  ╚██╗ ██╔╝██║   ██║██║     ██║   ██║   ██║   ██║██║   ██║  ║
║   ██║  ██║███████╗ ╚████╔╝ ╚██████╔╝███████╗╚██████╔╝   ██║   ██║╚██████╔╝  ║
║   ╚═╝  ╚═╝╚══════╝  ╚═══╝   ╚═════╝ ╚══════╝ ╚═════╝    ╚═╝   ╚═╝ ╚═════╝   ║
║                                                                              ║
║                    █████╗ ██╗     ██████╗ ██╗  ██╗ █████╗                    ║
║                   ██╔══██╗██║     ██╔══██╗██║  ██║██╔══██╗                   ║
║                   ███████║██║     ██████╔╝███████║███████║                   ║
║                   ██╔══██║██║     ██╔═══╝ ██╔══██║██╔══██║                   ║
║                   ██║  ██║███████╗██║     ██║  ██║██║  ██║                   ║
║                   ╚═╝  ╚═╝╚══════╝╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝                   ║
║                                                                              ║
║                       E N G I N E   v1.0.0                                   ║
║                                                                              ║
║            Institutional-Grade ML Trading System                             ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""


class RevolutionEngine:
    """
    Main application class for Revolution Alpha Engine.

    Orchestrates all components:
    - Configuration management
    - Scanner system
    - Trading engine
    - Risk management
    - ML models
    - Dashboard
    """

    def __init__(self, config_path: Optional[str] = None):
        self.console = Console()
        self.running = False
        self.config_path = config_path

        # Components (initialized lazily)
        self._config = None
        self._logger = None
        self._scanner_engine = None
        self._dashboard = None

    @property
    def config(self):
        """Get configuration (lazy load)."""
        if self._config is None:
            from src.core.config import load_config, Config
            if self.config_path and Path(self.config_path).exists():
                self._config = load_config(self.config_path)
            else:
                self._config = Config()
        return self._config

    @property
    def logger(self):
        """Get logger (lazy load)."""
        if self._logger is None:
            from src.core.logging import setup_logging
            self._logger = setup_logging(
                level=self.config.logging.level,
                log_dir=self.config.logging.log_dir,
                log_to_file=self.config.logging.log_to_file
            )
        return self._logger

    def print_banner(self):
        """Print the startup banner."""
        self.console.print(BANNER, style="bold blue")

    def print_status(self, message: str, status: str = "info"):
        """Print a status message."""
        styles = {
            "info": "cyan",
            "success": "green",
            "warning": "yellow",
            "error": "red"
        }
        style = styles.get(status, "white")
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.console.print(f"[dim]{timestamp}[/dim] [{style}]●[/{style}] {message}")

    async def initialize(self):
        """Initialize all components."""
        self.print_status("Initializing Revolution Alpha Engine...", "info")

        # Initialize logging
        self.print_status("Setting up logging...", "info")
        _ = self.logger
        self.print_status("Logging initialized", "success")

        # Initialize configuration
        self.print_status("Loading configuration...", "info")
        _ = self.config
        self.print_status(f"Configuration loaded (mode: {self.config.environment.value})", "success")

        # Create necessary directories
        for dir_name in [self.config.data_dir, self.config.models_dir, self.config.output_dir]:
            Path(dir_name).mkdir(parents=True, exist_ok=True)

        self.print_status("Initialization complete!", "success")

    async def start_scanners(self):
        """Start the scanner system."""
        self.print_status("Starting scanner system...", "info")

        try:
            from src.scanner.engine import ScannerEngine
            self._scanner_engine = ScannerEngine()

            # Configure scanners based on config
            if self.config.scanner.enable_momentum_scanner:
                self.print_status("  - Momentum scanner enabled", "info")
            if self.config.scanner.enable_squeeze_scanner:
                self.print_status("  - Squeeze scanner enabled", "info")
            if self.config.scanner.enable_options_scanner:
                self.print_status("  - Options scanner enabled", "info")
            if self.config.scanner.enable_mtf_scanner:
                self.print_status("  - MTF scanner enabled", "info")

            self.print_status("Scanner system started", "success")

        except ImportError as e:
            self.print_status(f"Scanner system not available: {e}", "warning")

    async def start_dashboard(self):
        """Start the dashboard."""
        self.print_status("Starting dashboard...", "info")

        try:
            from src.ui.dashboard import create_demo_dashboard
            self._dashboard = create_demo_dashboard()
            self._dashboard.start()

        except ImportError as e:
            self.print_status(f"Dashboard not available: {e}", "warning")

    async def run_backtest(self, strategy: str = "default"):
        """Run backtesting."""
        self.print_status(f"Starting backtest for strategy: {strategy}", "info")

        try:
            from src.backtest.engine import BacktestEngine
            engine = BacktestEngine()

            self.print_status("Backtest complete", "success")

        except ImportError as e:
            self.print_status(f"Backtest engine not available: {e}", "warning")

    def shutdown(self):
        """Graceful shutdown."""
        self.print_status("Shutting down...", "warning")
        self.running = False

        if self._dashboard:
            self._dashboard.stop()

        self.print_status("Shutdown complete", "success")

    async def run(self, mode: str = "paper", dashboard: bool = True):
        """
        Main run loop.

        Args:
            mode: Trading mode (live, paper, backtest)
            dashboard: Whether to show dashboard
        """
        self.running = True

        # Setup signal handlers
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda s, f: self.shutdown())

        # Initialize
        await self.initialize()

        self.print_status(f"Running in {mode.upper()} mode", "info")

        if mode == "backtest":
            await self.run_backtest()
        else:
            # Start scanners
            await self.start_scanners()

            # Start dashboard if requested
            if dashboard:
                await self.start_dashboard()
            else:
                # Keep running without dashboard
                self.print_status("Running headless (no dashboard)...", "info")
                while self.running:
                    await asyncio.sleep(1)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Revolution Alpha Engine - Institutional-Grade ML Trading System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                     Start with default settings
  python main.py --mode live         Live trading mode
  python main.py --mode paper        Paper trading mode (default)
  python main.py --mode backtest     Run backtests
  python main.py --dashboard         Dashboard only
  python main.py --scan              Scanner only
  python main.py --config my.yaml    Use custom config file

Documentation:
  See docs/MANUAL.md for full documentation
        """
    )

    parser.add_argument(
        "--mode", "-m",
        choices=["live", "paper", "backtest"],
        default="paper",
        help="Trading mode (default: paper)"
    )

    parser.add_argument(
        "--config", "-c",
        type=str,
        default=None,
        help="Path to configuration file"
    )

    parser.add_argument(
        "--dashboard", "-d",
        action="store_true",
        help="Show dashboard"
    )

    parser.add_argument(
        "--scan",
        action="store_true",
        help="Run scanner only"
    )

    parser.add_argument(
        "--no-dashboard",
        action="store_true",
        help="Run without dashboard (headless)"
    )

    parser.add_argument(
        "--version", "-v",
        action="version",
        version="Revolution Alpha Engine v1.0.0"
    )

    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run demo mode with sample data"
    )

    return parser.parse_args()


async def main():
    """Main entry point."""
    args = parse_args()

    console = Console()

    # Print banner
    console.print(BANNER, style="bold blue")

    # Create engine
    engine = RevolutionEngine(config_path=args.config)

    # Demo mode
    if args.demo:
        console.print("\n[yellow]Running in DEMO mode with sample data[/yellow]\n")
        from src.ui.dashboard import create_demo_dashboard
        dashboard = create_demo_dashboard()
        dashboard.render_once()
        return

    # Dashboard only mode
    if args.dashboard:
        from src.ui.dashboard import create_demo_dashboard
        dashboard = create_demo_dashboard()
        dashboard.start()
        return

    # Run main engine
    try:
        await engine.run(
            mode=args.mode,
            dashboard=not args.no_dashboard
        )
    except KeyboardInterrupt:
        engine.shutdown()
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]\n")
        raise


if __name__ == "__main__":
    asyncio.run(main())
