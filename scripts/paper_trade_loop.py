#!/usr/bin/env python3
"""
Scheduled / continuous paper-trading runner.

Re-runs the paper-trading simulation on a fixed interval, refreshing the
metrics, chart, and equity curve each cycle and appending one line per run to
artifacts/paper_run_history.jsonl. The underlying strategy is daily, so the
natural cadence is once per trading day; the interval is configurable for demos.

Usage:
    SCANIFY_FMP_API_KEY=... python scripts/paper_trade_loop.py            # default: daily
    SCANIFY_FMP_API_KEY=... python scripts/paper_trade_loop.py --interval 3600 --runs 5
    SCANIFY_FMP_API_KEY=... python scripts/paper_trade_loop.py --once     # single run

For unattended scheduling, prefer cron instead of a long-lived process, e.g.:
    30 16 * * 1-5  cd /path/to/repo && SCANIFY_FMP_API_KEY=... python scripts/paper_trade.py
"""
from __future__ import annotations

import argparse
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import paper_trade  # type: ignore  # noqa: E402  (sibling script)


def run_once() -> bool:
    try:
        res = paper_trade.main()
        print(f"  -> run ok: equity ${res['final_equity']:,.0f} "
              f"({res['total_return']:+.2%}), Sharpe {res['sharpe']:+.3f}")
        return True
    except SystemExit:
        raise
    except Exception:
        print("  -> run FAILED:\n" + traceback.format_exc())
        return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=86_400,
                    help="seconds between runs (default 86400 = 1 day)")
    ap.add_argument("--runs", type=int, default=0,
                    help="max runs (0 = run forever)")
    ap.add_argument("--once", action="store_true", help="run a single cycle and exit")
    args = ap.parse_args()

    if args.once:
        sys.exit(0 if run_once() else 1)

    n = 0
    print(f"Paper-trade loop started — interval {args.interval:.0f}s, "
          f"runs={'∞' if args.runs == 0 else args.runs}. Ctrl-C to stop.")
    try:
        while args.runs == 0 or n < args.runs:
            n += 1
            print(f"\n=== cycle {n} @ {datetime.now(timezone.utc).isoformat()} ===")
            run_once()
            if args.runs and n >= args.runs:
                break
            time.sleep(max(1.0, args.interval))
    except KeyboardInterrupt:
        print("\nStopped by user.")


if __name__ == "__main__":
    main()
