"""
Separate bot: institutional-flow scanner for NSE.

Fires only when ALL of these hold (see entry_setups.institutional_flow_signal):
  - RVOL >= INSTITUTIONAL_RVOL_THRESHOLD (default 40x)
  - the bar closed strong (near its high, not spike-and-fade)
  - volume is sustained over 2+ bars, not a single-bar artifact
  - price is making a fresh session high

...then separately checks for a same-day NSE catalyst (announcement, bulk
deal, block deal) and includes it in the alert either way -- if no catalyst
is found, the alert still fires but says so explicitly, since an unexplained
40x print is still worth knowing about, just with more caution attached.
"""

import time
import logging
from datetime import datetime, time as dtime
import requests
import pandas as pd
from fyers_apiv3 import fyersModel
from nse import NSE

from config_in import (
    FYERS_CLIENT_ID, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    INSTITUTIONAL_RVOL_THRESHOLD, CLOSE_STRENGTH_PCT,
    SUSTAINED_VOL_BARS, SUSTAINED_VOL_MULT, CATALYST_LOOKBACK_MINS,
    MIN_ELAPSED_MINS_FOR_RVOL, POLL_INTERVAL_SECONDS,
    SCAN_START_TIME, SCAN_END_TIME,
    ACCOUNT_CAPITAL, RISK_PER_TRADE_PCT, TARGET_R_MULTIPLE, SEND_CHART_SNAPSHOT,
)
from watchlist_store import load_watchlist
from fyers_auth import get_valid_token
from entry_setups import institutional_flow_signal
from catalyst_nse import get_today_catalysts, format_catalyst_summary
from alert_enrichment import compute_trade_plan, format_trade_plan_line, render_chart_snapshot
from alert_logger import log_alert, check_outcomes

def format_setup_note(levels: dict) -> str:
    """Appends the optional 'setup' and 'description' fields from the
    watchlist entry to an alert message, if present."""
    lines = ""
    setup = levels.get("setup")
    description = levels.get("description")
    if setup:
        lines += f"\n• *Setup:* {setup}"
    if description:
        lines += f"\n• *Note:* {description}"
    return lines

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def fyers_symbol_to_plain(symbol: str) -> str:
    """'NSE:RELIANCE-EQ' -> 'RELIANCE' (nse package wants the plain symbol)"""
    return symbol.split(":")[1].replace("-EQ", "")


class InstitutionalFlowScannerIN:
    def __init__(self):
        token = get_valid_token()
        self.fyers = fyersModel.FyersModel(client_id=FYERS_CLIENT_ID, token=token, is_async=False, log_path="")
        self.nse_client = NSE(download_folder="./nse_cache")  # one shared session for the whole run
        self.last_alert_bar = {}

    def fetch_5m_and_daily(self, symbol: str):
        today = datetime.now().strftime("%Y-%m-%d")
        sixty_days_ago = (datetime.now() - pd.Timedelta(days=60)).strftime("%Y-%m-%d")

        try:
            resp_5m = self.fyers.history(data={
                "symbol": symbol, "resolution": "5", "date_format": "1",
                "range_from": today, "range_to": today, "cont_flag": "1",
            })
            resp_d = self.fyers.history(data={
                "symbol": symbol, "resolution": "D", "date_format": "1",
                "range_from": sixty_days_ago, "range_to": today, "cont_flag": "1",
            })
        except Exception as e:
            logging.error(f"Fetch failed for {symbol}: {e}")
            return pd.DataFrame(), pd.DataFrame()

        def to_df(resp):
            if resp.get("s") != "ok" or not resp.get("candles"):
                return pd.DataFrame()
            df = pd.DataFrame(resp["candles"], columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s", utc=True).dt.tz_convert("Asia/Kolkata")
            return df.set_index("timestamp")

        return to_df(resp_5m), to_df(resp_d)

    def send_telegram_alert(self, message: str):
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
        try:
            requests.post(url, json=payload, timeout=5)
        except Exception as e:
            logging.error(f"Telegram alert failed: {e}")

    def send_telegram_photo(self, image_bytes: bytes, caption: str):
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        try:
            requests.post(
                url,
                data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption, "parse_mode": "Markdown"},
                files={"photo": ("chart.png", image_bytes, "image/png")},
                timeout=10,
            )
        except Exception as e:
            logging.error(f"Telegram photo failed: {e}")

    def send_alert(self, message: str, df=None, symbol="", entry=None, stop=None, target=None):
        if SEND_CHART_SNAPSHOT and df is not None and not df.empty:
            try:
                chart = render_chart_snapshot(df, symbol, entry_price=entry, stop_loss=stop, target=target)
                self.send_telegram_photo(chart, message)
                return
            except Exception as e:
                logging.error(f"Chart render failed for {symbol}, falling back to text: {e}")
        self.send_telegram_alert(message)

    def notify_resolved_alerts(self, symbol: str, df: pd.DataFrame):
        if df.empty:
            return
        for alert in check_outcomes("IN", symbol, df.iloc[-1]):
            hit_target = alert["new_status"] == "target_hit"
            emoji = "✅" if hit_target else "🛑"
            label = "TARGET HIT" if hit_target else "STOP HIT"
            r_txt = f"{alert['r_multiple']:.2f}R" if alert.get("r_multiple") is not None else "n/a"
            msg = (f"{emoji} *{label}*\n"
                   f"• *Symbol:* `{symbol}`\n"
                   f"• *Setup:* `{alert['setup_type']}`\n"
                   f"• *Entry:* `{alert['entry_price']}` → *Exit:* `{alert['exit_price']}`\n"
                   f"• *Result:* `{r_txt}`")
            self.send_telegram_alert(msg)

    def evaluate_symbol(self, symbol: str, levels: dict):
        df_5m, df_daily = self.fetch_5m_and_daily(symbol)
        if df_5m.empty or len(df_5m) < 15 or df_daily.empty or len(df_daily) < 15:
            return

        # Check open alerts against this bar first -- runs every poll regardless
        # of whether a new signal triggers below.
        self.notify_resolved_alerts(symbol, df_5m)

        daily_avg_vol = df_daily["volume"].iloc[-51:-1].mean()
        signal = institutional_flow_signal(
            df_5m, daily_avg_vol,
            rvol_threshold=INSTITUTIONAL_RVOL_THRESHOLD,
            close_strength_pct=CLOSE_STRENGTH_PCT,
            sustained_bars=SUSTAINED_VOL_BARS,
            sustained_mult=SUSTAINED_VOL_MULT,
        )

        if signal["rvol"]["elapsed_mins"] < MIN_ELAPSED_MINS_FOR_RVOL:
            return  # same early-session noise guard as the main scanner

        if not signal["triggered"]:
            return

        last_bar_ts = df_5m.index[-1]
        key = f"{symbol}_institutional"
        if self.last_alert_bar.get(key) == last_bar_ts:
            return  # already alerted this bar

        plain_symbol = fyers_symbol_to_plain(symbol)
        catalysts = get_today_catalysts(plain_symbol, self.nse_client)
        catalyst_line = format_catalyst_summary(catalysts)

        entry_price = signal["last_close"]
        stop_loss = round(df_5m["low"].min(), 2)  # session low so far -- same convention as the other setups
        plan = compute_trade_plan(entry_price, stop_loss, ACCOUNT_CAPITAL, RISK_PER_TRADE_PCT, TARGET_R_MULTIPLE)

        msg = (f"🏦 *INSTITUTIONAL FLOW ALERT*\n"
               f"• *Symbol:* `{symbol}`\n"
               f"• *RVOL:* `{signal['rvol']['rvol_ratio']}x`\n"
               f"• *Strong Close:* `{signal['close_strong']}`\n"
               f"• *Sustained Volume:* `{signal['volume_sustained']['sustained']}`\n"
               f"• *Fresh Session High:* `{signal['fresh_high']}`\n"
               f"• *Catalyst:* {catalyst_line}\n"
               f"{format_trade_plan_line(plan, currency_symbol='₹')}")
        msg += format_setup_note(levels)

        log_alert(market="IN", symbol=symbol, setup_type="institutional", entry_price=entry_price,
                  stop_loss=stop_loss, target_price=plan.get("target"), quantity=plan.get("quantity"),
                  rvol=signal["rvol"]["rvol_ratio"], catalyst_found=int(catalysts["has_catalyst"]),
                  bar_timestamp=str(last_bar_ts))
        self.send_alert(msg, df=df_5m, symbol=symbol, entry=entry_price, stop=stop_loss, target=plan.get("target"))
        self.last_alert_bar[key] = last_bar_ts

    def run_scanner_loop(self):
        logging.info("Starting India Institutional Flow Scanner...")
        start_h, start_m = map(int, SCAN_START_TIME.split(":"))
        end_h, end_m = map(int, SCAN_END_TIME.split(":"))
        scan_start, scan_end = dtime(start_h, start_m), dtime(end_h, end_m)

        while True:
            now = pd.Timestamp.now(tz="Asia/Kolkata").time()
            if scan_start <= now <= scan_end:
                # Reloaded every cycle so a corrected watchlist file (re-uploaded
                # mid-session) takes effect without restarting this process.
                for symbol, levels in load_watchlist().items():
                    self.evaluate_symbol(symbol, levels)
                time.sleep(POLL_INTERVAL_SECONDS)
            elif now < scan_start:
                time.sleep(60)
            else:
                logging.info("Scan window closed for the day. Exiting.")
                self.nse_client.exit()
                break


if __name__ == "__main__":
    scanner = InstitutionalFlowScannerIN()
    scanner.run_scanner_loop()
