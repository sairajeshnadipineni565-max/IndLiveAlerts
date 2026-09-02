# NSE Live Scanner (GitHub Actions edition)

Intraday Telegram alerting for NSE, using live Fyers broker data. Runs
automatically on GitHub's free Actions runners -- no VM, no cost, as long
as this repo is **public**.

**License:** All rights reserved (see `LICENSE`). This repo is public for
portfolio/demonstration purposes -- forking is a GitHub platform feature,
not permission to reuse the code.

## ⚠️ Before you make this repo public

If you ever ran an earlier version of this project, check `config_in.py`
in your git history for a hardcoded Fyers client secret or Telegram bot
token. If either is there, **rotate both**:
- Fyers: regenerate your secret key at https://myapi.fyers.in/dashboard/
- Telegram: @BotFather -> `/mybots` -> your bot -> API Token -> Revoke

An old commit with real credentials is still retrievable from a public
repo's history even if the current file is clean. This version's
`config_in.py` reads all secrets from environment variables only and never
contains a real credential, so it's safe to commit.

## One-time setup

1. **Push this folder to a public GitHub repo.**
2. **Add these repository secrets** (Settings -> Secrets and variables ->
   Actions -> New repository secret):
   - `FYERS_CLIENT_ID` -- from https://myapi.fyers.in/dashboard/
   - `FYERS_ACCESS_TOKEN` -- see "Daily use" below; you'll be updating this
     one every trading morning
   - `TELEGRAM_BOT_TOKEN` -- from @BotFather
   - `TELEGRAM_CHAT_ID` -- your chat ID
3. **Check Settings -> Actions -> General -> Workflow permissions** is set
   to "Read and write permissions" -- the workflows commit `alerts.db` back
   to the repo after each run, and need this to push.
4. That's it -- no server, no systemd, nothing to install anywhere.

`FYERS_SECRET_KEY` and `FYERS_REDIRECT_URI` are **not** GitHub Secrets --
they're only used by the local login step below, on your own machine.

## Daily use (two manual steps, ~1 min total before 9:15 AM IST)

Fyers tokens expire at market close, so there's no way around a daily
refresh -- but it stays on your machine, never in the repo or in GitHub's
secret store as a TOTP/PIN:

1. **Generate today's token** on your own machine:
   ```bash
   pip install -r requirements.txt
   export FYERS_CLIENT_ID="..."
   export FYERS_SECRET_KEY="..."
   export FYERS_REDIRECT_URI="..."
   python fyers_auth.py
   ```
   Follow the printed login URL, log into Fyers, paste back the `auth_code`
   from the redirect. It prints an access token.
2. **Paste that token into the `FYERS_ACCESS_TOKEN` GitHub Secret**
   (Settings -> Secrets and variables -> Actions -> `FYERS_ACCESS_TOKEN` ->
   Update). Fastest with the GitHub CLI: `gh secret set FYERS_ACCESS_TOKEN`.
3. **Upload today's watchlist** as `watchlist/<YYYY-MM-DD>.json` (IST date)
   -- see `watchlist/README.md` for the exact format. Easiest from the
   GitHub mobile app: repo -> `watchlist` -> `+` -> new file -> paste ->
   commit.

If you forget either step, the workflow fails fast with a clear message in
the Actions tab log rather than partway through the session -- check there
if you don't get any alerts by mid-morning.

| File | Purpose |
|---|---|
| `config_in.py` | Thresholds + secrets (secrets come from env, not this file) |
| `watchlist/` | Upload today's `<date>.json` here each morning |
| `watchlist_store.py` | Loads today's watchlist file |
| `fyers_auth.py` | Local daily login (`python fyers_auth.py`) + token lookup used by the scanners |
| `entry_setups.py` | Shared setup-detection logic |
| `pivot_cross_alert.py` | Instant pivot-level cross alert (no candle-color gate) |
| `catalyst_nse.py` | NSE announcements lookup |
| `alert_enrichment.py` | Chart snapshot + position sizing |
| `alert_logger.py` | SQLite logging of every alert (`alerts.db`, committed back to the repo by each workflow run) |
| `alert_report.py` | Win-rate / R-multiple report |
| `scanner_in.py` | Main scanning bot (breakout / undercut-rally / 30-min-pivot / pivot-cross / RVOL+9EMA / extreme volume) |
| `institutional_scanner_in.py` | Separate bot -- RVOL 40x+ institutional flow, with NSE-announcement catalyst check |
| `run_shift.py` | Runs both bots together for one shift -- what the workflows actually call |

## How the scheduling works

The full NSE session (9:15 AM-3:30 PM IST, 6h15m) is close enough to
GitHub Actions' 6-hour job cap that it's split into two shifts for safety
margin:

- **`.github/workflows/scanner-in-morning.yml`** -- 9:15 AM-12:30 PM IST
- **`.github/workflows/scanner-in-afternoon.yml`** -- 12:30-3:35 PM IST

Both bots (`scanner_in.py` + `institutional_scanner_in.py`) run
concurrently inside each shift via `run_shift.py`. IST has no daylight
saving, so (unlike the US version) each workflow only needs one cron
schedule year-round.

You can also trigger either shift manually any time from the repo's
**Actions** tab -> select the workflow -> **Run workflow**.

## Local testing

```bash
pip install -r requirements.txt
python fyers_auth.py                 # generates + caches today's token locally
export TELEGRAM_BOT_TOKEN="123:abc"
export TELEGRAM_CHAT_ID="123456"
export FYERS_CLIENT_ID="..."
python scanner_in.py                 # full session, one bot
python institutional_scanner_in.py   # full session, the other bot
python run_shift.py                  # both together, respects SCAN_START_TIME/SCAN_END_TIME if set
```

## Check performance

```bash
python alert_report.py IN
```

## Known limitation

Both bots write to the same `alerts.db` SQLite file. Running them
concurrently in one job (via threads in `run_shift.py`) can very
occasionally produce a "database is locked" error in the logs if both try
to write in the same instant -- harmless (the alert still fires to
Telegram either way).
