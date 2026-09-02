"""
Watchlist load, backed by a dated JSON file in watchlist/, uploaded manually
each day (GitHub web UI or app) before market open.

File naming: watchlist/<YYYY-MM-DD>.json using the IST calendar date. See
watchlist/README.md for the exact format.

Both scanner_in.py and institutional_scanner_in.py re-read this at the top
of every polling loop iteration, so if you fix a typo mid-session and
re-upload the file, it takes effect on the next poll -- no restart needed.
"""

import json
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

WATCHLIST_DIR = "watchlist"
IST = ZoneInfo("Asia/Kolkata")

_warned_missing_today = False


def _today_path() -> str:
    today = datetime.now(IST).strftime("%Y-%m-%d")
    return os.path.join(WATCHLIST_DIR, f"{today}.json")


def load_watchlist() -> dict:
    """Returns {} if today's file doesn't exist yet -- callers should treat
    an empty watchlist as "nothing to scan yet" and just wait for the next
    poll (e.g. file uploaded a few minutes late).

    Symbols must be in Fyers format: "NSE:<SYMBOL>-EQ" (e.g.
    "NSE:RELIANCE-EQ") -- see watchlist/README.md."""
    global _warned_missing_today
    path = _today_path()

    if not os.path.exists(path):
        if not _warned_missing_today:
            logging.warning(f"No watchlist file found at {path} -- upload today's "
                             f"list to watchlist/ before market open.")
            _warned_missing_today = True
        return {}

    try:
        with open(path, "r") as f:
            data = json.load(f)
        _warned_missing_today = False
        return data
    except (json.JSONDecodeError, OSError) as e:
        logging.error(f"Couldn't parse {path}: {e}")
        return {}
