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

from .visual_dashboard import (
    RevolutionDashboardV2,
    ASCIIChart,
    SignalPanel as SignalPanelV2,
    PerformancePanel as PerformancePanelV2,
    RiskPanel as RiskPanelV2,
    OrderBookPanel,
    HeaderPanel,
    ColorScheme,
    ChartConfig,
    create_dashboard as create_dashboard_v2,
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
    # Visual Dashboard V2
    "RevolutionDashboardV2",
    "ASCIIChart",
    "SignalPanelV2",
    "PerformancePanelV2",
    "RiskPanelV2",
    "OrderBookPanel",
    "HeaderPanel",
    "ColorScheme",
    "ChartConfig",
    "create_dashboard_v2",
]

__version__ = "0.1.0"
