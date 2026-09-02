"""
GitHub Actions version -- credentials come from environment variables
(set as GitHub Secrets), never hardcoded here. This file is safe to commit
to a public repo.

GitHub Secrets needed for the scheduled workflows (Settings -> Secrets and
variables -> Actions -> New repository secret):
    FYERS_CLIENT_ID      -- from https://myapi.fyers.in/dashboard/
    FYERS_ACCESS_TOKEN   -- pasted in fresh each trading morning; see fyers_auth.py
    TELEGRAM_BOT_TOKEN
    TELEGRAM_CHAT_ID

FYERS_SECRET_KEY and FYERS_REDIRECT_URI are only needed for the local,
interactive `python fyers_auth.py` login each morning -- they don't need to
be set as GitHub Secrets at all, since Actions never runs that flow.

For local testing, export whichever of the above you need in your shell.
"""

import os

# --- Fyers API ---
FYERS_CLIENT_ID = os.environ.get("FYERS_CLIENT_ID", "")
FYERS_SECRET_KEY = os.environ.get("FYERS_SECRET_KEY", "")       # local auth only
FYERS_REDIRECT_URI = os.environ.get("FYERS_REDIRECT_URI", "")   # local auth only

# --- Telegram (from @BotFather) ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    raise RuntimeError(
        "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set. "
        "Set them as GitHub Secrets (Actions workflow) or export them locally."
    )

# --- Scanner tuning ---
RVOL_THRESHOLD = 1.5
EXTREME_RVOL_THRESHOLD = 10.0
MIN_ELAPSED_MINS_FOR_RVOL = 15
EMA_TOLERANCE_PCT = 0.3
POLL_INTERVAL_SECONDS = 60

# NSE market hours: 09:15 - 15:30 IST. Overridable per-shift by the GitHub
# Actions workflow (each shift job sets these env vars so a single scanner
# run stays under GitHub's 6-hour job limit -- see .github/workflows/).
SCAN_START_TIME = os.environ.get("SCAN_START_TIME", "09:15")
SCAN_END_TIME = os.environ.get("SCAN_END_TIME", "15:30")

# --- Institutional Flow scanner ---
INSTITUTIONAL_RVOL_THRESHOLD = 40
CLOSE_STRENGTH_PCT = 75
SUSTAINED_VOL_BARS = 2
SUSTAINED_VOL_MULT = 1.3
CATALYST_LOOKBACK_MINS = 30

# --- Alert enrichment ---
ACCOUNT_CAPITAL = 100000
RISK_PER_TRADE_PCT = 1.0
TARGET_R_MULTIPLE = 2.0
SEND_CHART_SNAPSHOT = True

# --- Watchlist ---
# Loaded from watchlist/<YYYY-MM-DD>.json (IST date) each poll -- see
# watchlist_store.py and watchlist/README.md. Upload that day's file to the
# watchlist/ folder before market open (GitHub web UI or app).
