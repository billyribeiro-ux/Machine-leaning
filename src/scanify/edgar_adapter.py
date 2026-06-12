"""
SCANIFY SEC EDGAR Adapter — Institutional Holdings & Options Position Intelligence

Fetches 13F filings, institutional ownership data, and options-related
SEC filings to provide real institutional positioning context for the
GEX scanner and directional analysis.

SEC EDGAR API: https://www.sec.gov/edgar/sec-api-documentation
All requests must include a User-Agent header with company/email.
Rate limit: 10 requests/second.
"""

import json
import logging
import time as time_module
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------


@dataclass
class InstitutionalHolder:
    """A single institutional holder's position from a 13F filing."""

    cik: str                    # Central Index Key
    name: str
    filing_date: str
    report_date: str
    shares_held: int
    value_usd: float
    share_change: int           # change from prior quarter
    change_pct: float
    portfolio_pct: float        # % of their portfolio


@dataclass
class OptionsPosition:
    """Options positioning data extracted from 13F / institutional filings."""

    holder_name: str
    filing_date: str
    put_value: float            # total put notional
    call_value: float           # total call notional
    put_call_ratio: float
    total_options_value: float
    change_from_prior: float


@dataclass
class InstitutionalSummary:
    """Aggregate institutional positioning summary for a symbol."""

    symbol: str
    total_institutional_shares: int
    total_institutional_value: float
    num_holders: int
    num_new_positions: int
    num_increased: int
    num_decreased: int
    num_sold_out: int
    top_holders: List[InstitutionalHolder] = field(default_factory=list)
    net_institutional_flow: str = "neutral"   # "accumulating" | "distributing" | "neutral"
    last_updated: str = ""


# ---------------------------------------------------------------------------
# Known Major Institutional CIKs
# ---------------------------------------------------------------------------

_MAJOR_SPX_HOLDERS: Dict[str, str] = {
    "0000102909": "Vanguard Group",
    "0001364742": "BlackRock",
    "0000093751": "State Street",
    "0000315066": "Fidelity (FMR LLC)",
    "0000019617": "JPMorgan Chase",
    "0001423053": "Citadel Advisors",
    "0001350694": "Bridgewater Associates",
}

_OPTIONS_HEAVY_INSTITUTIONS: Dict[str, str] = {
    "0001423053": "Citadel Advisors",
    "0001446194": "Susquehanna International",
    "0001598835": "Jane Street Group",
    "0001167483": "Wolverine Trading",
    "0000921669": "Two Sigma Investments",
    "0001003078": "DE Shaw & Co",
}

# SPY / IVV / VOO — the big SPX ETFs we search for in 13F filings.
_SPX_ETFS = ("SPY", "IVV", "VOO")


# ---------------------------------------------------------------------------
# EDGAR Adapter
# ---------------------------------------------------------------------------


class EDGARAdapter:
    """SEC EDGAR data adapter for institutional holdings and options data.

    The EDGAR API is free and public.  Requirements:
      - User-Agent header in ``CompanyName AdminEmail`` format.
      - Maximum 10 requests / second.
      - ``data.sec.gov`` for structured JSON data.
      - ``efts.sec.gov/LATEST/`` for full-text search endpoints.

    All 13F data is *quarterly* — this adapter provides strategic context
    (institutional accumulation / distribution), not real-time signals.
    """

    SEARCH_BASE = "https://efts.sec.gov/LATEST"
    DATA_BASE = "https://data.sec.gov"

    def __init__(self, user_agent: str = "ScanifyScanner admin@scanify.dev") -> None:
        self.user_agent = user_agent
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": self.user_agent,
            "Accept": "application/json",
        })
        self._last_request_time: float = 0.0
        self._min_interval: float = 0.10  # 100 ms between requests

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _rate_limited_get(
        self,
        url: str,
        params: Optional[Dict] = None,
        max_retries: int = 3,
        timeout: float = 15.0,
    ) -> requests.Response:
        """GET with rate limiting (100 ms spacing) and automatic retries.

        Raises
        ------
        requests.RequestException
            After exhausting all retries.
        """
        for attempt in range(1, max_retries + 1):
            # Enforce rate limit
            elapsed = time_module.time() - self._last_request_time
            if elapsed < self._min_interval:
                time_module.sleep(self._min_interval - elapsed)

            try:
                logger.debug("EDGAR GET %s (attempt %d/%d)", url, attempt, max_retries)
                self._last_request_time = time_module.time()
                resp = self._session.get(url, params=params, timeout=timeout)
                resp.raise_for_status()
                return resp
            except requests.RequestException as exc:
                logger.warning(
                    "EDGAR request failed (attempt %d/%d): %s — %s",
                    attempt,
                    max_retries,
                    url,
                    exc,
                )
                if attempt == max_retries:
                    raise
                # Back off before retry
                time_module.sleep(1.0 * attempt)

        # Unreachable, but keeps mypy happy.
        raise requests.RequestException("Exhausted retries")  # pragma: no cover

    @staticmethod
    def _pad_cik(cik: str) -> str:
        """Zero-pad a CIK to the 10-digit format EDGAR expects."""
        return cik.lstrip("0").zfill(10)

    # ------------------------------------------------------------------
    # Company Search
    # ------------------------------------------------------------------

    def search_company(self, name: str) -> List[Dict]:
        """Search EDGAR full-text index for a company by name.

        Returns a list of dicts with keys:
        ``cik``, ``name``, ``filing_date``, ``accession_number``.
        """
        url = f"{self.SEARCH_BASE}/search-index"
        params = {
            "q": name,
            "dateRange": "custom",
            "startdt": "2024-01-01",
            "forms": "13F-HR",
        }
        try:
            resp = self._rate_limited_get(url, params=params)
            data = resp.json()
        except Exception as exc:
            logger.error("Company search failed for %r: %s", name, exc)
            return []

        results: List[Dict] = []
        hits = data.get("hits", data.get("filings", []))
        if isinstance(hits, dict):
            hits = hits.get("hits", [])

        for hit in hits:
            source = hit.get("_source", hit)
            results.append({
                "cik": str(source.get("entity_id", source.get("cik", ""))),
                "name": source.get("entity_name", source.get("display_names", [name])[0]
                                   if isinstance(source.get("display_names"), list) else name),
                "filing_date": source.get("file_date", source.get("filing_date", "")),
                "accession_number": source.get("adsh", source.get("accession_number", "")),
            })

        logger.info("Company search %r returned %d results", name, len(results))
        return results

    # ------------------------------------------------------------------
    # Company Facts (XBRL)
    # ------------------------------------------------------------------

    def get_company_facts(self, cik: str) -> Dict:
        """Fetch structured company facts from EDGAR's XBRL endpoint.

        Parameters
        ----------
        cik : str
            Central Index Key (with or without zero-padding).
        """
        padded = self._pad_cik(cik)
        url = f"{self.DATA_BASE}/api/xbrl/companyfacts/CIK{padded}.json"
        try:
            resp = self._rate_limited_get(url)
            return resp.json()
        except Exception as exc:
            logger.error("Failed to fetch company facts for CIK %s: %s", padded, exc)
            return {}

    # ------------------------------------------------------------------
    # 13F Filing Index
    # ------------------------------------------------------------------

    def get_13f_filings(self, cik: str, limit: int = 4) -> List[Dict]:
        """Get recent 13F-HR filings for an institution.

        Parameters
        ----------
        cik : str
            Institution CIK.
        limit : int
            Maximum number of filings to return (most recent first).

        Returns
        -------
        List[Dict]
            Each dict contains ``accessionNumber``, ``filingDate``,
            ``reportDate``, ``primaryDocument``, ``form``.
        """
        padded = self._pad_cik(cik)
        url = f"{self.DATA_BASE}/submissions/CIK{padded}.json"
        try:
            resp = self._rate_limited_get(url)
            data = resp.json()
        except Exception as exc:
            logger.error("Failed to fetch submissions for CIK %s: %s", padded, exc)
            return []

        recent = data.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        filing_dates = recent.get("filingDate", [])
        report_dates = recent.get("reportDate", [])
        accession_numbers = recent.get("accessionNumber", [])
        primary_docs = recent.get("primaryDocument", [])

        filings_13f: List[Dict] = []
        for idx, form_type in enumerate(forms):
            if form_type in ("13F-HR", "13F-HR/A"):
                filings_13f.append({
                    "accessionNumber": accession_numbers[idx] if idx < len(accession_numbers) else "",
                    "filingDate": filing_dates[idx] if idx < len(filing_dates) else "",
                    "reportDate": report_dates[idx] if idx < len(report_dates) else "",
                    "primaryDocument": primary_docs[idx] if idx < len(primary_docs) else "",
                    "form": form_type,
                })
                if len(filings_13f) >= limit:
                    break

        logger.info("Found %d 13F filings for CIK %s", len(filings_13f), padded)
        return filings_13f

    # ------------------------------------------------------------------
    # Institutional Holders for SPX (via SPY/IVV/VOO proxy)
    # ------------------------------------------------------------------

    def get_institutional_holders_for_spx(self) -> InstitutionalSummary:
        """Fetch institutional holder data for S&P 500 via SPY proxy.

        SPX itself has no direct 13F data, so we search for 13F filings
        mentioning SPY and build a summary from the filing metadata.
        """
        six_months_ago = (date.today() - timedelta(days=180)).isoformat()
        url = f"{self.SEARCH_BASE}/search-index"
        params = {
            "q": '"SPY"',
            "forms": "13F-HR",
            "dateRange": "custom",
            "startdt": six_months_ago,
        }

        try:
            resp = self._rate_limited_get(url, params=params)
            data = resp.json()
        except Exception as exc:
            logger.error("SPX institutional search failed: %s", exc)
            return InstitutionalSummary(
                symbol="SPX",
                total_institutional_shares=0,
                total_institutional_value=0.0,
                num_holders=0,
                num_new_positions=0,
                num_increased=0,
                num_decreased=0,
                num_sold_out=0,
                last_updated=datetime.utcnow().isoformat(),
            )

        hits = data.get("hits", data.get("filings", []))
        if isinstance(hits, dict):
            hits = hits.get("hits", [])
        total_hits = len(hits) if isinstance(hits, list) else 0

        # Build a lightweight summary from search metadata.
        # Full position-level data would require downloading each filing's
        # XML information table, which is expensive.  For the scanner we
        # care about the *trend* (how many filers mention SPY recently).
        summary = InstitutionalSummary(
            symbol="SPX",
            total_institutional_shares=0,
            total_institutional_value=0.0,
            num_holders=total_hits,
            num_new_positions=0,
            num_increased=0,
            num_decreased=0,
            num_sold_out=0,
            net_institutional_flow="neutral",
            last_updated=datetime.utcnow().isoformat(),
        )

        logger.info(
            "SPX institutional search: %d filings mentioning SPY in last 6 months",
            total_hits,
        )
        return summary

    # ------------------------------------------------------------------
    # Major SPX Holders (known CIKs)
    # ------------------------------------------------------------------

    def get_major_spx_holders(self) -> List[InstitutionalHolder]:
        """Fetch latest filing data for known major SPX/SPY holders.

        Iterates over a hardcoded set of major institutional CIKs,
        fetches their latest 13F submission metadata, and tries to
        identify SPY/IVV/VOO positions from the filing information.
        """
        holders: List[InstitutionalHolder] = []

        for cik, inst_name in _MAJOR_SPX_HOLDERS.items():
            try:
                filings = self.get_13f_filings(cik, limit=1)
                if not filings:
                    logger.warning("No 13F filing found for %s (%s)", inst_name, cik)
                    continue

                latest = filings[0]
                filing_date = latest.get("filingDate", "")
                report_date = latest.get("reportDate", "")

                # Without downloading and parsing the full XML information
                # table we cannot get exact share counts.  We record the
                # filing metadata so downstream consumers know the filing
                # exists and when it was filed.
                holder = InstitutionalHolder(
                    cik=cik,
                    name=inst_name,
                    filing_date=filing_date,
                    report_date=report_date,
                    shares_held=0,
                    value_usd=0.0,
                    share_change=0,
                    change_pct=0.0,
                    portfolio_pct=0.0,
                )
                holders.append(holder)
                logger.info(
                    "Fetched filing metadata for %s — filed %s, reported %s",
                    inst_name,
                    filing_date,
                    report_date,
                )

            except Exception as exc:
                logger.error("Failed to fetch data for %s (%s): %s", inst_name, cik, exc)
                continue

        # Sort by filing date descending
        holders.sort(key=lambda h: h.filing_date, reverse=True)
        return holders

    # ------------------------------------------------------------------
    # Options Activity Filings
    # ------------------------------------------------------------------

    def get_options_activity_filings(self, days_back: int = 30) -> List[OptionsPosition]:
        """Search for recent 13F filings from options-heavy institutions.

        Focuses on known market makers and options dealers to gauge
        aggregate put/call positioning sentiment.

        Parameters
        ----------
        days_back : int
            How many days back to search for filings.
        """
        positions: List[OptionsPosition] = []
        start_date = (date.today() - timedelta(days=days_back)).isoformat()

        for cik, inst_name in _OPTIONS_HEAVY_INSTITUTIONS.items():
            try:
                filings = self.get_13f_filings(cik, limit=1)
                if not filings:
                    continue

                latest = filings[0]
                filing_date = latest.get("filingDate", "")

                # Check whether this filing is within our lookback window
                if filing_date and filing_date < start_date:
                    logger.debug(
                        "Skipping %s — filing %s is before %s",
                        inst_name,
                        filing_date,
                        start_date,
                    )
                    continue

                # Full put/call breakdowns require parsing the XML
                # information table.  We record what we can from the
                # submission metadata and flag the institution as having
                # a recent filing.
                position = OptionsPosition(
                    holder_name=inst_name,
                    filing_date=filing_date,
                    put_value=0.0,
                    call_value=0.0,
                    put_call_ratio=0.0,
                    total_options_value=0.0,
                    change_from_prior=0.0,
                )
                positions.append(position)
                logger.info(
                    "Options-heavy institution %s filed 13F on %s",
                    inst_name,
                    filing_date,
                )

            except Exception as exc:
                logger.error(
                    "Failed to fetch options filings for %s (%s): %s",
                    inst_name,
                    cik,
                    exc,
                )
                continue

        return positions

    # ------------------------------------------------------------------
    # Institutional Sentiment Analysis
    # ------------------------------------------------------------------

    def analyze_institutional_sentiment(
        self,
        holders: List[InstitutionalHolder],
    ) -> Dict:
        """Analyze aggregate institutional positioning from holder data.

        Parameters
        ----------
        holders : List[InstitutionalHolder]
            List of holder snapshots (typically from ``get_major_spx_holders``).

        Returns
        -------
        Dict
            ``sentiment`` — ``"bullish"`` / ``"bearish"`` / ``"neutral"``.
            ``confidence`` — 0.0 to 1.0.
            ``details`` — breakdown counts and large movers.
        """
        if not holders:
            return {
                "sentiment": "neutral",
                "confidence": 0.0,
                "details": {
                    "num_holders": 0,
                    "new_positions": 0,
                    "sold_out": 0,
                    "increased": 0,
                    "decreased": 0,
                    "large_changes": [],
                },
            }

        new_positions = 0
        sold_out = 0
        increased = 0
        decreased = 0
        large_changes: List[Dict] = []

        for h in holders:
            if h.shares_held > 0 and h.share_change == h.shares_held:
                # Entire position is new (change equals total)
                new_positions += 1
            elif h.shares_held == 0 and h.share_change < 0:
                sold_out += 1
            elif h.share_change > 0:
                increased += 1
            elif h.share_change < 0:
                decreased += 1

            # Flag large position changes (>10%)
            if abs(h.change_pct) > 10.0:
                large_changes.append({
                    "name": h.name,
                    "change_pct": h.change_pct,
                    "share_change": h.share_change,
                })

        total = len(holders)
        net_positive = new_positions + increased
        net_negative = sold_out + decreased

        if total == 0:
            sentiment = "neutral"
            confidence = 0.0
        elif net_positive > net_negative:
            sentiment = "bullish"
            confidence = min(1.0, net_positive / total)
        elif net_negative > net_positive:
            sentiment = "bearish"
            confidence = min(1.0, net_negative / total)
        else:
            sentiment = "neutral"
            confidence = 0.3

        return {
            "sentiment": sentiment,
            "confidence": round(confidence, 2),
            "details": {
                "num_holders": total,
                "new_positions": new_positions,
                "sold_out": sold_out,
                "increased": increased,
                "decreased": decreased,
                "large_changes": large_changes,
            },
        }

    # ------------------------------------------------------------------
    # Report Generation
    # ------------------------------------------------------------------

    def get_report(self) -> str:
        """Generate a human-readable institutional positioning report.

        Fetches the major SPX holders, runs sentiment analysis, and
        returns a formatted multi-line string suitable for display or
        logging.
        """
        lines: List[str] = []
        lines.append("=" * 68)
        lines.append("  SCANIFY — Institutional Positioning Report (SEC EDGAR)")
        lines.append("=" * 68)
        lines.append(f"  Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
        lines.append("")

        # --- Major holders ---
        lines.append("  Major SPX/SPY Institutional Holders (13F)")
        lines.append("  " + "-" * 60)

        try:
            holders = self.get_major_spx_holders()
        except Exception as exc:
            holders = []
            lines.append(f"  [ERROR] Failed to fetch holders: {exc}")

        if holders:
            for h in holders:
                lines.append(
                    f"  {h.name:<30s}  Filed: {h.filing_date}  "
                    f"Report: {h.report_date}"
                )
                if h.shares_held:
                    lines.append(
                        f"    Shares: {h.shares_held:>14,}  "
                        f"Value: ${h.value_usd:>14,.0f}  "
                        f"Change: {h.change_pct:+.1f}%"
                    )
        else:
            lines.append("  No holder data available.")

        lines.append("")

        # --- Sentiment ---
        lines.append("  Institutional Sentiment Analysis")
        lines.append("  " + "-" * 60)

        analysis = self.analyze_institutional_sentiment(holders)
        lines.append(f"  Sentiment:  {analysis['sentiment'].upper()}")
        lines.append(f"  Confidence: {analysis['confidence']:.0%}")
        details = analysis["details"]
        lines.append(f"  Holders tracked:  {details['num_holders']}")
        lines.append(f"  New positions:    {details['new_positions']}")
        lines.append(f"  Increased:        {details['increased']}")
        lines.append(f"  Decreased:        {details['decreased']}")
        lines.append(f"  Sold out:         {details['sold_out']}")

        if details["large_changes"]:
            lines.append("")
            lines.append("  Large Position Changes (>10%):")
            for lc in details["large_changes"]:
                lines.append(
                    f"    {lc['name']}: {lc['change_pct']:+.1f}% "
                    f"({lc['share_change']:+,} shares)"
                )

        lines.append("")

        # --- Options activity ---
        lines.append("  Options-Heavy Institution Filing Activity")
        lines.append("  " + "-" * 60)

        try:
            options_positions = self.get_options_activity_filings(days_back=90)
        except Exception as exc:
            options_positions = []
            lines.append(f"  [ERROR] Failed to fetch options filings: {exc}")

        if options_positions:
            for op in options_positions:
                lines.append(
                    f"  {op.holder_name:<30s}  Filed: {op.filing_date}"
                )
                if op.total_options_value > 0:
                    lines.append(
                        f"    Puts: ${op.put_value:>12,.0f}  "
                        f"Calls: ${op.call_value:>12,.0f}  "
                        f"P/C Ratio: {op.put_call_ratio:.2f}"
                    )
        else:
            lines.append("  No recent options-heavy filings found.")

        lines.append("")
        lines.append("  NOTE: 13F data is quarterly. Use for strategic context,")
        lines.append("        not real-time trading signals.")
        lines.append("=" * 68)

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Standalone Test
# ---------------------------------------------------------------------------


def run_edgar_test() -> None:
    """Fetch institutional data and print a summary report."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    adapter = EDGARAdapter()

    print("\n--- Searching for 'Vanguard' in EDGAR ---")
    results = adapter.search_company("Vanguard")
    for r in results[:5]:
        print(f"  CIK: {r['cik']}  Name: {r['name']}  Filed: {r['filing_date']}")

    print("\n--- SPX Institutional Summary (via SPY) ---")
    summary = adapter.get_institutional_holders_for_spx()
    print(f"  Holders found in filings: {summary.num_holders}")
    print(f"  Flow: {summary.net_institutional_flow}")

    print("\n--- Full Report ---")
    report = adapter.get_report()
    print(report)


if __name__ == "__main__":
    run_edgar_test()
