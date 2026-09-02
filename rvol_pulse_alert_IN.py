"""
RVOL Pulse alert -- the loosest alert type on purpose. It checks relative
volume ONLY: no EMA proximity, no candle color, no key level, no trade
plan. Meant as an early "something's stirring" ping, not a trade signal --
no entry/stop/target is computed or logged for outcome tracking, unlike
the other setups.

RVOL_PULSE_THRESHOLD = 1.10 means volume is running >=10% above normal for
this point in the session -- much looser than RVOL_THRESHOLD (1.5x) used by
the standard RVOL+9EMA alert, so expect this one to fire far more often.

Throttling: the poll loop runs every 60 seconds, but this alert should only
actually notify once every RVOL_PULSE_INTERVAL_MINUTES per symbol. Rather
than track a separate timer, scanner_us.py/scanner_in.py reuse the existing
dispatch_if_new_bar dedup mechanism (the same one-alert-per-bar logic the
other setups use) by keying off a wall-clock time bucket instead of an
actual price bar -- see time_bucket() below.
"""

RVOL_PULSE_THRESHOLD = 1.10
RVOL_PULSE_INTERVAL_MINUTES = 10


def time_bucket(now, interval_minutes: int = RVOL_PULSE_INTERVAL_MINUTES):
    """Rounds `now` down to the nearest `interval_minutes` mark, e.g.
    9:47 -> 9:40 for a 10-minute bucket (with now.second/microsecond
    zeroed out too, so two calls within the same bucket return an
    identical value). Passed as the dedup key to dispatch_if_new_bar, so
    this alert fires at most once per bucket per symbol regardless of how
    many times per bucket the poll loop actually checks it."""
    floored_minute = (now.minute // interval_minutes) * interval_minutes
    return now.replace(minute=floored_minute, second=0, microsecond=0)
