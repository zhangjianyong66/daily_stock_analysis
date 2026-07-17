#!/usr/bin/env python3
"""Quarantine or restore historical SearXNG business news rows."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.storage import get_db  # noqa: E402


DEFAULT_BATCH = "searxng-retirement-20260717"
DEFAULT_REASON = "private_searxng_retired_untrusted_results"


def _parse_datetime(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("时间必须是 ISO-8601 格式") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("quarantine", "rollback"))
    parser.add_argument("--batch", default=DEFAULT_BATCH)
    parser.add_argument("--before", type=_parse_datetime, default=datetime.now())
    parser.add_argument("--reason", default=DEFAULT_REASON)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    db = get_db()
    if args.action == "quarantine":
        count = db.quarantine_news_intel(
            provider="SearXNG",
            before=args.before,
            batch=args.batch,
            reason=args.reason,
            dry_run=args.dry_run,
        )
    else:
        count = db.rollback_news_intel_quarantine(
            batch=args.batch,
            dry_run=args.dry_run,
        )
    mode = "dry-run" if args.dry_run else "applied"
    print(f"action={args.action} mode={mode} batch={args.batch} rows={count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
