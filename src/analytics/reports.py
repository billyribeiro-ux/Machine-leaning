"""
Revolution Alpha Engine - Report Generator

Professional report generation with multiple export formats:
- CSV exports for all data
- PDF reports with charts and analysis
- Word documents for detailed reports
- JSON for data interchange
- Excel workbooks with multiple sheets
"""

import pandas as pd
import numpy as np
from typing import Optional, List, Dict, Any, Union
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
import json
import csv
import io
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


@dataclass
class ReportMetadata:
    """Metadata for generated reports."""
    title: str
    generated_at: datetime
    generated_by: str = "Revolution Alpha Engine"
    version: str = "1.0.0"
    report_type: str = "backtest"

    def to_dict(self) -> Dict[str, Any]:
        return {
            'title': self.title,
            'generated_at': self.generated_at.isoformat(),
            'generated_by': self.generated_by,
            'version': self.version,
            'report_type': self.report_type
        }


class ReportSection:
    """A section of a report."""

    def __init__(self, title: str, content_type: str = "text"):
        self.title = title
        self.content_type = content_type
        self.content: Any = None
        self.subsections: List['ReportSection'] = []

    def set_text(self, text: str):
        self.content_type = "text"
        self.content = text

    def set_table(self, df: pd.DataFrame):
        self.content_type = "table"
        self.content = df

    def set_metrics(self, metrics: Dict[str, Any]):
        self.content_type = "metrics"
        self.content = metrics

    def set_chart_data(self, data: Dict[str, Any]):
        self.content_type = "chart"
        self.content = data

    def add_subsection(self, section: 'ReportSection'):
        self.subsections.append(section)


class BaseReportGenerator(ABC):
    """Abstract base class for report generators."""

    def __init__(self, output_dir: str = "./reports"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @abstractmethod
    def generate(self, data: Any, filename: str) -> str:
        """Generate report and return file path."""
        pass


class CSVReportGenerator(BaseReportGenerator):
    """Generate CSV reports."""

    def generate(
        self,
        data: Union[pd.DataFrame, List[Dict], Dict[str, pd.DataFrame]],
        filename: str
    ) -> str:
        """
        Generate CSV report.

        Args:
            data: DataFrame, list of dicts, or dict of DataFrames
            filename: Output filename (without extension)

        Returns:
            Path to generated file
        """
        filepath = self.output_dir / f"{filename}.csv"

        if isinstance(data, pd.DataFrame):
            data.to_csv(filepath, index=True)
        elif isinstance(data, list):
            df = pd.DataFrame(data)
            df.to_csv(filepath, index=False)
        elif isinstance(data, dict):
            # Multiple dataframes - create multiple files
            for key, df in data.items():
                subpath = self.output_dir / f"{filename}_{key}.csv"
                if isinstance(df, pd.DataFrame):
                    df.to_csv(subpath, index=True)

        logger.info(f"CSV report generated: {filepath}")
        return str(filepath)

    def generate_trades_report(
        self,
        trades: List[Any],
        filename: str = "trades_report"
    ) -> str:
        """Generate detailed trades CSV report."""
        records = []

        for trade in trades:
            record = {
                'trade_id': trade.trade_id,
                'symbol': trade.symbol,
                'direction': trade.direction.value if hasattr(trade.direction, 'value') else trade.direction,
                'entry_time': trade.entry_time.isoformat() if trade.entry_time else None,
                'exit_time': trade.exit_time.isoformat() if trade.exit_time else None,
                'entry_price': trade.entry_price,
                'exit_price': trade.exit_price,
                'stop_loss': trade.stop_loss,
                'take_profit': trade.take_profit,
                'shares': trade.shares,
                'position_value': trade.position_value,
                'gross_pnl': trade.gross_pnl,
                'commission': trade.commission,
                'slippage': trade.slippage,
                'net_pnl': trade.net_pnl,
                'pnl_pct': trade.pnl_pct,
                'r_multiple': trade.r_multiple,
                'exit_reason': trade.exit_reason,
                'max_adverse_excursion': trade.max_adverse_excursion,
                'max_favorable_excursion': trade.max_favorable_excursion,
            }

            # Add diagnostic info
            if trade.diagnostic:
                record['primary_reason'] = trade.diagnostic.primary_reason
                record['trend_alignment'] = trade.diagnostic.trend_alignment
                record['momentum_status'] = trade.diagnostic.momentum_status
                record['entry_quality'] = trade.diagnostic.entry_timing_quality
                record['rsi_at_entry'] = trade.diagnostic.rsi_at_entry
                record['macd_at_entry'] = trade.diagnostic.macd_at_entry

            records.append(record)

        return self.generate(records, filename)


class JSONReportGenerator(BaseReportGenerator):
    """Generate JSON reports."""

    def generate(
        self,
        data: Any,
        filename: str,
        pretty: bool = True
    ) -> str:
        """Generate JSON report."""
        filepath = self.output_dir / f"{filename}.json"

        def serialize(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            elif isinstance(obj, pd.DataFrame):
                return obj.to_dict(orient='records')
            elif isinstance(obj, np.ndarray):
                return obj.tolist()
            elif hasattr(obj, 'to_dict'):
                return obj.to_dict()
            elif hasattr(obj, '__dict__'):
                return obj.__dict__
            return str(obj)

        with open(filepath, 'w') as f:
            json.dump(data, f, default=serialize, indent=2 if pretty else None)

        logger.info(f"JSON report generated: {filepath}")
        return str(filepath)


class MarkdownReportGenerator(BaseReportGenerator):
    """Generate Markdown reports (can be converted to PDF/DOC)."""

    def generate(
        self,
        sections: List[ReportSection],
        filename: str,
        metadata: Optional[ReportMetadata] = None
    ) -> str:
        """Generate Markdown report."""
        filepath = self.output_dir / f"{filename}.md"

        lines = []

        # Title
        if metadata:
            lines.append(f"# {metadata.title}")
            lines.append("")
            lines.append(f"*Generated: {metadata.generated_at.strftime('%Y-%m-%d %H:%M:%S')}*")
            lines.append(f"*By: {metadata.generated_by} v{metadata.version}*")
            lines.append("")
            lines.append("---")
            lines.append("")

        # Sections
        for section in sections:
            lines.extend(self._render_section(section, level=2))

        with open(filepath, 'w') as f:
            f.write('\n'.join(lines))

        logger.info(f"Markdown report generated: {filepath}")
        return str(filepath)

    def _render_section(self, section: ReportSection, level: int) -> List[str]:
        """Render a section to markdown lines."""
        lines = []
        header = '#' * level

        lines.append(f"{header} {section.title}")
        lines.append("")

        if section.content_type == "text":
            lines.append(section.content)
            lines.append("")

        elif section.content_type == "table":
            lines.extend(self._render_table(section.content))
            lines.append("")

        elif section.content_type == "metrics":
            lines.extend(self._render_metrics(section.content))
            lines.append("")

        elif section.content_type == "chart":
            lines.append("*[Chart data available in exported files]*")
            lines.append("")

        # Subsections
        for subsection in section.subsections:
            lines.extend(self._render_section(subsection, level + 1))

        return lines

    def _render_table(self, df: pd.DataFrame) -> List[str]:
        """Render DataFrame as markdown table."""
        if df.empty:
            return ["*No data*", ""]

        lines = []

        # Header
        headers = ['Index'] + list(df.columns) if df.index.name or not df.index.equals(pd.RangeIndex(len(df))) else list(df.columns)
        lines.append("| " + " | ".join(str(h) for h in headers) + " |")
        lines.append("| " + " | ".join("---" for _ in headers) + " |")

        # Rows (limit to first 50)
        for idx, row in df.head(50).iterrows():
            if df.index.name or not df.index.equals(pd.RangeIndex(len(df))):
                values = [str(idx)] + [self._format_value(v) for v in row]
            else:
                values = [self._format_value(v) for v in row]
            lines.append("| " + " | ".join(values) + " |")

        if len(df) > 50:
            lines.append(f"*... and {len(df) - 50} more rows*")

        return lines

    def _render_metrics(self, metrics: Dict[str, Any]) -> List[str]:
        """Render metrics as markdown list."""
        lines = []
        for key, value in metrics.items():
            formatted_key = key.replace('_', ' ').title()
            formatted_value = self._format_value(value)
            lines.append(f"- **{formatted_key}:** {formatted_value}")
        return lines

    def _format_value(self, value: Any) -> str:
        """Format a value for display."""
        if isinstance(value, float):
            if abs(value) >= 1000:
                return f"{value:,.2f}"
            elif abs(value) < 0.01:
                return f"{value:.6f}"
            else:
                return f"{value:.4f}"
        elif isinstance(value, datetime):
            return value.strftime('%Y-%m-%d %H:%M:%S')
        elif value is None:
            return "N/A"
        return str(value)


class HTMLReportGenerator(BaseReportGenerator):
    """Generate HTML reports with styling."""

    def generate(
        self,
        sections: List[ReportSection],
        filename: str,
        metadata: Optional[ReportMetadata] = None
    ) -> str:
        """Generate HTML report."""
        filepath = self.output_dir / f"{filename}.html"

        html = self._generate_html(sections, metadata)

        with open(filepath, 'w') as f:
            f.write(html)

        logger.info(f"HTML report generated: {filepath}")
        return str(filepath)

    def _generate_html(
        self,
        sections: List[ReportSection],
        metadata: Optional[ReportMetadata]
    ) -> str:
        """Generate HTML content."""
        css = self._get_css()

        title = metadata.title if metadata else "Report"

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>{css}</style>
</head>
<body>
    <div class="container">
        <header>
            <h1>{title}</h1>
            <p class="meta">Generated: {metadata.generated_at.strftime('%Y-%m-%d %H:%M:%S') if metadata else datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </header>
        <main>
"""

        for section in sections:
            html += self._render_section_html(section)

        html += """
        </main>
        <footer>
            <p>Generated by Revolution Alpha Engine</p>
        </footer>
    </div>
</body>
</html>"""

        return html

    def _render_section_html(self, section: ReportSection, level: int = 2) -> str:
        """Render section as HTML."""
        html = f"<section>\n<h{level}>{section.title}</h{level}>\n"

        if section.content_type == "text":
            html += f"<p>{section.content}</p>\n"

        elif section.content_type == "table":
            html += self._render_table_html(section.content)

        elif section.content_type == "metrics":
            html += self._render_metrics_html(section.content)

        for subsection in section.subsections:
            html += self._render_section_html(subsection, level + 1)

        html += "</section>\n"
        return html

    def _render_table_html(self, df: pd.DataFrame) -> str:
        """Render DataFrame as HTML table."""
        if df.empty:
            return "<p><em>No data</em></p>"

        return df.to_html(classes='data-table', border=0, index=True)

    def _render_metrics_html(self, metrics: Dict[str, Any]) -> str:
        """Render metrics as HTML."""
        html = '<div class="metrics-grid">\n'

        for key, value in metrics.items():
            formatted_key = key.replace('_', ' ').title()

            # Determine value styling
            value_class = "metric-value"
            if isinstance(value, (int, float)):
                if value > 0:
                    value_class += " positive"
                elif value < 0:
                    value_class += " negative"

            formatted_value = self._format_value(value)

            html += f"""
            <div class="metric-card">
                <div class="metric-label">{formatted_key}</div>
                <div class="{value_class}">{formatted_value}</div>
            </div>
"""

        html += '</div>\n'
        return html

    def _format_value(self, value: Any) -> str:
        """Format value for display."""
        if isinstance(value, float):
            if abs(value) >= 1000:
                return f"{value:,.2f}"
            return f"{value:.2f}"
        elif isinstance(value, datetime):
            return value.strftime('%Y-%m-%d %H:%M')
        elif value is None:
            return "N/A"
        return str(value)

    def _get_css(self) -> str:
        """Get CSS styles for HTML report."""
        return """
            * { margin: 0; padding: 0; box-sizing: border-box; }

            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
                line-height: 1.6;
                color: #333;
                background: #f5f5f5;
            }

            .container {
                max-width: 1200px;
                margin: 0 auto;
                background: white;
                min-height: 100vh;
            }

            header {
                background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
                color: white;
                padding: 40px;
                text-align: center;
            }

            header h1 {
                font-size: 2.5rem;
                margin-bottom: 10px;
            }

            header .meta {
                opacity: 0.8;
            }

            main {
                padding: 40px;
            }

            section {
                margin-bottom: 40px;
            }

            h2 {
                color: #1e3c72;
                border-bottom: 2px solid #2a5298;
                padding-bottom: 10px;
                margin-bottom: 20px;
            }

            h3 {
                color: #444;
                margin: 20px 0 10px;
            }

            .metrics-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 20px;
                margin: 20px 0;
            }

            .metric-card {
                background: #f8f9fa;
                border-radius: 8px;
                padding: 20px;
                text-align: center;
                border: 1px solid #e9ecef;
            }

            .metric-label {
                font-size: 0.9rem;
                color: #666;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }

            .metric-value {
                font-size: 1.8rem;
                font-weight: bold;
                color: #333;
                margin-top: 5px;
            }

            .metric-value.positive { color: #28a745; }
            .metric-value.negative { color: #dc3545; }

            .data-table {
                width: 100%;
                border-collapse: collapse;
                margin: 20px 0;
            }

            .data-table th, .data-table td {
                padding: 12px;
                text-align: left;
                border-bottom: 1px solid #ddd;
            }

            .data-table th {
                background: #f8f9fa;
                font-weight: 600;
                color: #333;
            }

            .data-table tr:hover {
                background: #f5f5f5;
            }

            footer {
                background: #333;
                color: white;
                text-align: center;
                padding: 20px;
            }

            @media print {
                .container { max-width: none; }
                header { background: #333; }
            }
        """


class ReportManager:
    """
    Central report management system.

    Coordinates generation of all report types.
    """

    def __init__(self, output_dir: str = "./reports"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.csv_generator = CSVReportGenerator(str(self.output_dir / "csv"))
        self.json_generator = JSONReportGenerator(str(self.output_dir / "json"))
        self.markdown_generator = MarkdownReportGenerator(str(self.output_dir / "markdown"))
        self.html_generator = HTMLReportGenerator(str(self.output_dir / "html"))

    def generate_backtest_report(
        self,
        results: Any,
        formats: List[str] = ["csv", "json", "html", "md"]
    ) -> Dict[str, str]:
        """
        Generate comprehensive backtest report in multiple formats.

        Args:
            results: BacktestResults object
            formats: List of formats to generate

        Returns:
            Dictionary of format -> file path
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"backtest_report_{timestamp}"

        generated_files = {}

        metadata = ReportMetadata(
            title=f"Backtest Report - {results.start_date.date()} to {results.end_date.date()}",
            generated_at=datetime.now(),
            report_type="backtest"
        )

        # Build report sections
        sections = self._build_backtest_sections(results)

        if "csv" in formats:
            # Generate multiple CSV files
            trades_path = self.csv_generator.generate_trades_report(results.trades, f"{filename}_trades")
            equity_path = self.csv_generator.generate(results.equity_curve, f"{filename}_equity")
            generated_files['csv_trades'] = trades_path
            generated_files['csv_equity'] = equity_path

        if "json" in formats:
            json_data = self._prepare_json_data(results)
            generated_files['json'] = self.json_generator.generate(json_data, filename)

        if "md" in formats:
            generated_files['md'] = self.markdown_generator.generate(sections, filename, metadata)

        if "html" in formats:
            generated_files['html'] = self.html_generator.generate(sections, filename, metadata)

        logger.info(f"Generated {len(generated_files)} report files")
        return generated_files

    def _build_backtest_sections(self, results: Any) -> List[ReportSection]:
        """Build report sections from backtest results."""
        sections = []

        # Executive Summary
        summary = ReportSection("Executive Summary")
        summary.set_text(
            f"This backtest was conducted from {results.start_date.date()} to {results.end_date.date()}, "
            f"starting with ${results.initial_capital:,.2f} in capital. "
            f"The strategy generated a total return of {results.total_return_pct:.2f}% "
            f"with a maximum drawdown of {results.max_drawdown:.2f}%."
        )
        sections.append(summary)

        # Performance Metrics
        perf = ReportSection("Performance Metrics")
        perf.set_metrics({
            'initial_capital': f"${results.initial_capital:,.2f}",
            'final_capital': f"${results.final_capital:,.2f}",
            'total_return': f"${results.total_return:,.2f}",
            'total_return_pct': f"{results.total_return_pct:.2f}%",
            'annual_return': f"{results.annual_return:.2f}%",
            'sharpe_ratio': f"{results.sharpe_ratio:.2f}",
            'sortino_ratio': f"{results.sortino_ratio:.2f}",
            'calmar_ratio': f"{results.calmar_ratio:.2f}",
            'max_drawdown': f"{results.max_drawdown:.2f}%",
        })
        sections.append(perf)

        # Trade Statistics
        trades = ReportSection("Trade Statistics")
        trades.set_metrics({
            'total_trades': results.total_trades,
            'winning_trades': results.winning_trades,
            'losing_trades': results.losing_trades,
            'win_rate': f"{results.win_rate:.2f}%",
            'profit_factor': f"{results.profit_factor:.2f}",
            'avg_win': f"${results.avg_win:,.2f}",
            'avg_loss': f"${results.avg_loss:,.2f}",
            'largest_win': f"${results.largest_win:,.2f}",
            'largest_loss': f"${results.largest_loss:,.2f}",
            'avg_r_multiple': f"{results.avg_r_multiple:.2f}R",
            'expectancy': f"${results.expectancy:,.2f}",
        })
        sections.append(trades)

        # Trade List
        if results.trades:
            trade_list = ReportSection("Trade Details")
            trade_df = pd.DataFrame([t.to_dict() for t in results.trades[:100]])
            trade_list.set_table(trade_df)
            sections.append(trade_list)

        return sections

    def _prepare_json_data(self, results: Any) -> Dict[str, Any]:
        """Prepare data for JSON export."""
        return {
            'metadata': {
                'generated_at': datetime.now().isoformat(),
                'start_date': results.start_date.isoformat(),
                'end_date': results.end_date.isoformat(),
                'backtest_id': results.backtest_id,
            },
            'performance': {
                'initial_capital': results.initial_capital,
                'final_capital': results.final_capital,
                'total_return': results.total_return,
                'total_return_pct': results.total_return_pct,
                'annual_return': results.annual_return,
                'max_drawdown': results.max_drawdown,
                'sharpe_ratio': results.sharpe_ratio,
                'sortino_ratio': results.sortino_ratio,
                'calmar_ratio': results.calmar_ratio,
            },
            'trade_statistics': {
                'total_trades': results.total_trades,
                'winning_trades': results.winning_trades,
                'losing_trades': results.losing_trades,
                'win_rate': results.win_rate,
                'profit_factor': results.profit_factor,
                'avg_win': results.avg_win,
                'avg_loss': results.avg_loss,
                'expectancy': results.expectancy,
            },
            'trades': [t.to_dict() for t in results.trades],
            'equity_curve': results.equity_curve.reset_index().to_dict(orient='records'),
        }

    def generate_signal_report(
        self,
        signals: List[Any],
        filename: str = "signals_report"
    ) -> Dict[str, str]:
        """Generate signal analysis report."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{filename}_{timestamp}"

        # Convert signals to records
        records = []
        for signal in signals:
            record = {
                'timestamp': signal.timestamp.isoformat() if hasattr(signal, 'timestamp') else None,
                'symbol': signal.symbol,
                'direction': signal.direction,
                'confidence': signal.confidence,
                'entry_price': signal.entry_price,
                'stop_loss': signal.stop_loss,
                'take_profit': signal.take_profit,
                'scanner_type': getattr(signal, 'scanner_type', 'unknown'),
            }

            if hasattr(signal, 'reasons'):
                record['reasons'] = '; '.join(signal.reasons)

            records.append(record)

        generated = {}

        generated['csv'] = self.csv_generator.generate(records, filename)
        generated['json'] = self.json_generator.generate(records, filename)

        return generated
