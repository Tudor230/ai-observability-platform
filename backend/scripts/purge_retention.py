"""Apply the configured retention window (AIOBS_RETENTION_DAYS) to the DB.

Usage:
    uv run python scripts/purge_retention.py
"""
from __future__ import annotations

import sys

from aiobs_backend import db
from aiobs_backend.config import get_settings
from aiobs_backend.retention import purge_expired


def main() -> int:
    days = get_settings().retention_days
    with db.session_scope() as session:
        result = purge_expired(session, days)
    print({"retention_days": days, **result})
    return 0


if __name__ == "__main__":
    sys.exit(main())
