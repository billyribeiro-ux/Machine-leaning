#!/usr/bin/env python3
"""
Verify the Schwab connection after OAuth (scripts/schwab_login.py).

Pulls a live quote, recent daily bars, and an SPX option-chain snapshot to
confirm the access/refresh token flow and market-data endpoints work.

Usage:
    python scripts/schwab_check.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / ".env")

from src.scanify.schwab_adapter import SchwabAdapter  # noqa: E402


def main() -> None:
    s = SchwabAdapter()
    print("configured:", s.is_configured, "| has_refresh_token:", s.has_refresh_token)
    if not s.has_refresh_token:
        print("No refresh token yet — run: python scripts/schwab_login.py")
        sys.exit(1)

    print("\n[1] Quote AAPL ...")
    q = s.get_quote("AAPL")
    print("   ", {k: q.get(k) for k in list(q)[:4]} if isinstance(q, dict) else q)

    print("[2] Daily bars SPY (last 3) ...")
    bars = s.get_historical_daily("SPY", limit=4000)
    for b in bars[-3:]:
        print("   ", b)

    print("[3] SPX option chain (count) ...")
    try:
        chain = s.fetch_spx_options_chain()
        print(f"    {len(chain.quotes)} quotes, underlying={chain.underlying_price:.2f}")
    except Exception as exc:
        print("    options chain error:", exc)

    print("\nSchwab connection OK." if bars else "\nNo data returned — check entitlements.")


if __name__ == "__main__":
    main()
