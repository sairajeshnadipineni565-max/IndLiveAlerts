"""
Simple pivot-level cross alert.

This is deliberately separate from the existing "30-Min Pivot" setup in
entry_setups.py (check_30min_pivot), which only fires on a *green 30-minute
candle* breaking above the pivot level -- meaning it can lag up to 30
minutes and needs that candle-color condition to be true.

This one is a plain price-cross check on 5-minute bars (checked every poll,
so effectively within ~60 seconds of the actual cross): it fires the moment
the last close moves from below the pivot_level to at/above it. No candle
color, no volume condition -- just "did it cross."

Both can be active on the same ticker/pivot_level at once (they're wired
in as separate setups with separate dedup keys in scanner_us.py) -- you'll
get this one first (faster), and possibly the 30-min one too if a green
30m candle later confirms it. If you only want one, remove the other's
block from scanner_us.py's evaluate_symbol.
"""


def check_pivot_cross(df_5m_today, pivot_level: float) -> dict:
    """
    df_5m_today: today's 5-minute bars (open/high/low/close/volume), most
        recent bar last.
    pivot_level: the price to watch for a cross above. None/0 is treated as
        "not set" -- caller should skip calling this if so.

    Returns {"triggered": bool, "stop_loss": float or None}.

    "triggered" is only True on the bar where the cross actually happens
    (prior bar's close below the level, current bar's close at/above it) --
    not on every subsequent bar while price stays above, so you get exactly
    one alert per cross rather than one every poll.

    stop_loss is the low of the crossing bar, in line with the stop
    convention used by the other setups in entry_setups.py (session low /
    triggering-bar low as a simple initial stop).
    """
    if df_5m_today is None or df_5m_today.empty or len(df_5m_today) < 2 or not pivot_level:
        return {"triggered": False, "stop_loss": None}

    last_close = df_5m_today["close"].iloc[-1]
    prev_close = df_5m_today["close"].iloc[-2]

    triggered = bool(prev_close < pivot_level <= last_close)
    stop_loss = round(float(df_5m_today["low"].iloc[-1]), 2) if triggered else None

    return {"triggered": triggered, "stop_loss": stop_loss}
