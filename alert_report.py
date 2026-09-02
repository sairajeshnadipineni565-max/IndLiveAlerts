"""
Performance summary across logged alerts, grouped by setup type.

Usage:
    python alert_report.py            # both markets
    python alert_report.py IN         # India only
    python alert_report.py US         # US only
"""

import sys
import sqlite3
from alert_logger import DB_PATH, init_db


def main():
    market_filter = sys.argv[1].upper() if len(sys.argv) > 1 else None
    init_db()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    query = "SELECT * FROM alerts"
    params = ()
    if market_filter:
        query += " WHERE market = ?"
        params = (market_filter,)
    rows = [dict(r) for r in conn.execute(query, params).fetchall()]
    conn.close()

    if not rows:
        print("No alerts logged yet.")
        return

    by_setup = {}
    for r in rows:
        by_setup.setdefault(r["setup_type"], []).append(r)

    header = f"{'Setup':<16}{'Total':<8}{'Resolved':<10}{'Wins':<7}{'Win%':<8}{'Avg R':<8}{'Total PnL':<12}"
    print(header)
    print("-" * len(header))

    for setup, alerts in sorted(by_setup.items()):
        resolved = [a for a in alerts if a["status"] != "open"]
        wins = [a for a in resolved if a["status"] == "target_hit"]
        r_values = [a["r_multiple_achieved"] for a in resolved if a["r_multiple_achieved"] is not None]
        pnl_values = [a["pnl"] for a in resolved if a["pnl"] is not None]

        avg_r = sum(r_values) / len(r_values) if r_values else 0.0
        win_pct = (len(wins) / len(resolved) * 100) if resolved else 0.0
        total_pnl = sum(pnl_values) if pnl_values else 0.0

        print(f"{setup:<16}{len(alerts):<8}{len(resolved):<10}{len(wins):<7}"
              f"{win_pct:<8.1f}{avg_r:<8.2f}{total_pnl:<12.2f}")

    open_count = sum(1 for r in rows if r["status"] == "open")
    print(f"\n{open_count} alert(s) still open (no target/stop hit yet).")


if __name__ == "__main__":
    main()
