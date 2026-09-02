"""
Shared alert logging + outcome tracking, using SQLite (zero setup, single
file, free). Every scanner logs each alert it fires here, and every
scanner's loop checks open alerts against each new bar to auto-resolve them
as target_hit / stop_hit -- so months from now you can actually answer
"which setup is working" with numbers, instead of guessing from memory.

All four scanners share the same DB file (alerts.db, created alongside
wherever you run them) so alert_report.py can summarize across both markets.
"""

import sqlite3
from datetime import datetime
from contextlib import contextmanager

DB_PATH = "alerts.db"


@contextmanager
def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                logged_at TEXT NOT NULL,
                market TEXT NOT NULL,                  -- 'IN' or 'US'
                symbol TEXT NOT NULL,
                setup_type TEXT NOT NULL,              -- breakout / unr / 30m_pivot / institutional
                entry_price REAL,
                stop_loss REAL,
                target_price REAL,
                quantity INTEGER,
                rvol REAL,
                catalyst_found INTEGER,                -- 1/0/NULL
                bar_timestamp TEXT,
                status TEXT NOT NULL DEFAULT 'open',   -- open / target_hit / stop_hit
                exit_price REAL,
                exit_at TEXT,
                r_multiple_achieved REAL,
                pnl REAL
            )
        """)


def log_alert(market, symbol, setup_type, entry_price, stop_loss=None, target_price=None,
              quantity=None, rvol=None, catalyst_found=None, bar_timestamp=None) -> int:
    init_db()
    with _connect() as conn:
        cur = conn.execute("""
            INSERT INTO alerts (logged_at, market, symbol, setup_type, entry_price, stop_loss,
                                 target_price, quantity, rvol, catalyst_found, bar_timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (datetime.now().isoformat(), market, symbol, setup_type, entry_price, stop_loss,
              target_price, quantity, rvol, catalyst_found, bar_timestamp))
        return cur.lastrowid


def get_open_alerts(market: str, symbol: str = None):
    init_db()
    with _connect() as conn:
        if symbol:
            rows = conn.execute(
                "SELECT * FROM alerts WHERE market=? AND symbol=? AND status='open'",
                (market, symbol)).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM alerts WHERE market=? AND status='open'", (market,)).fetchall()
        return [dict(r) for r in rows]


def _resolve(alert_id: int, status: str, exit_price: float) -> dict:
    with _connect() as conn:
        row = conn.execute("SELECT entry_price, stop_loss, quantity FROM alerts WHERE id=?",
                            (alert_id,)).fetchone()
        entry, stop, qty = row["entry_price"], row["stop_loss"], row["quantity"] or 0
        risk_per_share = abs(entry - stop) if (entry is not None and stop is not None and entry != stop) else None
        r_multiple = ((exit_price - entry) / risk_per_share) if risk_per_share else None
        pnl = (exit_price - entry) * qty if qty else None

        conn.execute("""
            UPDATE alerts SET status=?, exit_price=?, exit_at=?, r_multiple_achieved=?, pnl=?
            WHERE id=?
        """, (status, exit_price, datetime.now().isoformat(), r_multiple, pnl, alert_id))

        return {"r_multiple": r_multiple, "pnl": pnl}


def check_outcomes(market: str, symbol: str, latest_bar) -> list:
    """
    Checks all open alerts for `symbol` against latest_bar's high/low and
    resolves any that were hit. latest_bar needs .high / .low attributes
    (a pandas Series row works) or dict-like 'high'/'low' keys.

    NOTE on same-bar ambiguity: if a single bar's range spans BOTH the stop
    and the target, OHLC data alone can't tell you which was hit first --
    this assumes stop was hit first (the conservative assumption) rather
    than guessing favorably.

    Returns a list of dicts, one per alert resolved this call, each merging
    the original alert fields with 'new_status', 'exit_price', 'r_multiple',
    'pnl' -- ready for the caller to build a follow-up notification from.
    """
    high = latest_bar["high"] if isinstance(latest_bar, dict) else latest_bar.high
    low = latest_bar["low"] if isinstance(latest_bar, dict) else latest_bar.low

    resolved = []
    for alert in get_open_alerts(market, symbol):
        target, stop = alert["target_price"], alert["stop_loss"]

        if stop is not None and low <= stop:
            outcome = _resolve(alert["id"], "stop_hit", stop)
            resolved.append({**alert, "new_status": "stop_hit", "exit_price": stop, **outcome})
        elif target is not None and high >= target:
            outcome = _resolve(alert["id"], "target_hit", target)
            resolved.append({**alert, "new_status": "target_hit", "exit_price": target, **outcome})

    return resolved
