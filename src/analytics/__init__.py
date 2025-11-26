"""
Revolution Alpha Engine - Analytics & Dashboard

Interactive analytics and reporting:
- Rich terminal UI dashboard
- Real-time signal monitoring
- Performance visualization
- Customizable risk settings
- Multi-format report generation (CSV, JSON, HTML, Markdown)
- Backtest analysis dashboards
"""

from .dashboard import (
    RevolutionDashboard,
    SignalPanel,
    PerformancePanel,
    RiskPanel,
    BacktestDashboard,
    RiskSettingsMenu,
    DashboardConfig,
    create_dashboard,
)

from .reports import (
    ReportManager,
    BaseReportGenerator,
    CSVReportGenerator,
    JSONReportGenerator,
    MarkdownReportGenerator,
    HTMLReportGenerator,
    ReportConfig,
    create_report_manager,
)

__all__ = [
    # Dashboard
    "RevolutionDashboard",
    "SignalPanel",
    "PerformancePanel",
    "RiskPanel",
    "BacktestDashboard",
    "RiskSettingsMenu",
    "DashboardConfig",
    "create_dashboard",
    # Reports
    "ReportManager",
    "BaseReportGenerator",
    "CSVReportGenerator",
    "JSONReportGenerator",
    "MarkdownReportGenerator",
    "HTMLReportGenerator",
    "ReportConfig",
    "create_report_manager",
]

__version__ = "0.1.0"
