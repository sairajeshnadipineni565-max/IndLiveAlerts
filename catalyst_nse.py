"""
NSE catalyst lookup -- corporate announcements and bulk/block deals filed
today, using the free `nse` package (pip install nse).

This is what turns a raw institutional-flow volume signal into "RVOL 40x
AND there's a real filed reason" rather than just "RVOL 40x" -- see the
discussion of why raw volume alone false-positives on halts, block trades,
and low-float spikes.

NOTE: nse.NSE() maintains its own cookie/session file in download_folder --
reuse a single NSE() instance across a whole scan cycle (don't create a new
one per symbol) to avoid re-establishing the session repeatedly.
"""

from datetime import datetime
from nse import NSE


def get_today_catalysts(symbol: str, nse_client: NSE) -> dict:
    """
    Returns any announcements or bulk/block deals for `symbol` filed today.
    Symbol should be the plain NSE symbol (e.g. "RELIANCE"), not the Fyers
    "NSE:RELIANCE-EQ" format used elsewhere in the scanner.
    """
    now = datetime.now()
    today_start = datetime(now.year, now.month, now.day)

    result = {"announcements": [], "bulk_deals": [], "block_deals": []}

    try:
        result["announcements"] = nse_client.announcements(symbol=symbol,
                                                             from_date=today_start, to_date=now) or []
    except Exception:
        pass  # announcement fetch failing shouldn't block the volume alert itself

    try:
        bulk = nse_client.bulkdeals(option_type="bulk_deals", fromdate=today_start, todate=now) or []
        result["bulk_deals"] = [d for d in bulk if d.get("symbol") == symbol]
    except Exception:
        pass

    try:
        block = nse_client.bulkdeals(option_type="block_deals", fromdate=today_start, todate=now) or []
        result["block_deals"] = [d for d in block if d.get("symbol") == symbol]
    except Exception:
        pass

    result["has_catalyst"] = bool(result["announcements"] or result["bulk_deals"] or result["block_deals"])
    return result


def format_catalyst_summary(catalysts: dict) -> str:
    """Short human-readable line for a Telegram message."""
    if not catalysts["has_catalyst"]:
        return "No filed announcement/deal found -- treat with extra caution"

    parts = []
    if catalysts["announcements"]:
        subjects = [a.get("subject", a.get("desc", "announcement")) for a in catalysts["announcements"][:2]]
        parts.append("Announcement: " + "; ".join(subjects))
    if catalysts["bulk_deals"]:
        parts.append(f"{len(catalysts['bulk_deals'])} bulk deal(s) today")
    if catalysts["block_deals"]:
        parts.append(f"{len(catalysts['block_deals'])} block deal(s) today")
    return " | ".join(parts)
