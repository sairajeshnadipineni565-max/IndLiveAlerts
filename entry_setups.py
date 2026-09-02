"""
Entry setup detectors for the swing-trading watchlist scanner.

All functions take pandas DataFrames with columns: open, high, low, close, volume
and a DatetimeIndex. Timeframe-specific resampling (1m -> 5m -> 30m -> daily) is
the caller's job (the Fyers data-fetch layer) -- these functions just detect.

NOTE ON "KEY LEVELS": Setup 1 (Breakout) and Setup 2 (Undercut & Rally) both
reference a "key resistance/support level" that in your own trade examples
(CIFR 19.50, LUMN 8.24, HOOD 120) you identify manually from chart study --
that's a judgment call, not something safely auto-detected from price alone.
So these functions expect you to supply that level per ticker (via your
existing watchlist / chart-study workflow) rather than trying to infer a
trendline or S/R zone algorithmically. Everything else -- compression,
volume spike, candle-close conditions, EMA proximity -- is computed live.
"""

import pandas as pd
import numpy as np


# ---------------------------------------------------------------------------
# 1. Relative Volume (ported from your Pine Script -- "IBD RVOL Adj")
# ---------------------------------------------------------------------------

def relative_volume(intraday_df: pd.DataFrame, daily_avg_vol: float,
                     session_start="09:15", session_end="15:30",
                     tz="Asia/Kolkata") -> dict:
    """
    Pacing-adjusted RVOL, session-aware.

    intraday_df   : today's intraday bars so far (any interval), needs 'volume'
    daily_avg_vol : N-day average daily volume for the ticker (precomputed
                    from daily bars, EXCLUDING today -- matches volume[1] in Pine)
    session_start/session_end : local session times as "HH:MM"
    tz            : session timezone -- "Asia/Kolkata" for NSE (09:15-15:30),
                    "America/New_York" for US markets (09:30-16:00)

    Returns today's cumulative volume, projected EOD volume, rvol_ratio, rvol_pct.
    """
    now = pd.Timestamp.now(tz=tz)
    sess_start = pd.Timestamp.combine(now.date(), pd.Timestamp(session_start).time()).tz_localize(tz)
    sess_end = pd.Timestamp.combine(now.date(), pd.Timestamp(session_end).time()).tz_localize(tz)
    total_session_mins = (sess_end - sess_start).total_seconds() / 60  # 375 for NSE, 390 for US

    elapsed_mins = max((now - sess_start).total_seconds() / 60, 0)
    is_active = 0 < elapsed_mins < total_session_mins
    pct_completed = (elapsed_mins / total_session_mins) if is_active else 1.0
    pct_completed = max(pct_completed, 0.01)  # guard div-by-zero right at open

    cum_volume = intraday_df["volume"].sum()
    proj_volume = cum_volume / pct_completed if is_active else cum_volume

    rvol_ratio = proj_volume / daily_avg_vol if daily_avg_vol else np.nan
    rvol_pct = ((proj_volume - daily_avg_vol) / daily_avg_vol) * 100 if daily_avg_vol else np.nan

    return {
        "cum_volume": cum_volume,
        "proj_volume": proj_volume,
        "rvol_ratio": round(rvol_ratio, 2),
        "rvol_pct": round(rvol_pct, 2),
        "pct_day_completed": round(pct_completed * 100, 1),
        "elapsed_mins": round(elapsed_mins, 1),
    }


# ---------------------------------------------------------------------------
# 2. EMA proximity (pass in daily bars for a "9-day" pullback like your
#    @ohiain-style notes, or intraday bars for an intraday 9EMA retest)
# ---------------------------------------------------------------------------

def near_ema(df: pd.DataFrame, length=9, tolerance_pct=0.3) -> dict:
    """True if the latest close is within tolerance_pct% of the EMA(length)."""
    ema = df["close"].ewm(span=length, adjust=False).mean()
    last_close = df["close"].iloc[-1]
    last_ema = ema.iloc[-1]
    pct_diff = abs(last_close - last_ema) / last_ema * 100

    return {
        "ema_value": round(last_ema, 2),
        "last_close": round(last_close, 2),
        "pct_diff": round(pct_diff, 2),
        "is_near": pct_diff <= tolerance_pct,
        "above_ema": last_close >= last_ema,
    }


# ---------------------------------------------------------------------------
# 3. Setup 1 -- Breakout Entry Model
#    Daily: compression + declining volume. 5-min: break of key resistance
#    with a volume spike.
# ---------------------------------------------------------------------------

def is_compressing(daily_df: pd.DataFrame, lookback=10, atr_len=14) -> dict:
    """
    Auto-computable proxy for 'compression with declining volume':
    - ATR% (ATR / close) trending down over the lookback window
    - Average volume over the last `lookback` days trending down vs the
      `lookback` days before that
    """
    high, low, close = daily_df["high"], daily_df["low"], daily_df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(atr_len).mean()
    atr_pct = (atr / close) * 100

    recent_atr_pct = atr_pct.iloc[-lookback:]
    atr_contracting = recent_atr_pct.iloc[-1] < recent_atr_pct.iloc[0]

    recent_vol_avg = daily_df["volume"].iloc[-lookback:].mean()
    prior_vol_avg = daily_df["volume"].iloc[-2 * lookback:-lookback].mean()
    volume_declining = recent_vol_avg < prior_vol_avg

    return {
        "atr_pct_now": round(recent_atr_pct.iloc[-1], 2),
        "atr_contracting": atr_contracting,
        "volume_declining": volume_declining,
        "is_compressing": atr_contracting and volume_declining,
    }


def check_breakout_entry(daily_df: pd.DataFrame, intraday_5m_df: pd.DataFrame,
                          key_resistance: float, vol_spike_mult=1.5,
                          lookback=10) -> dict:
    """
    key_resistance : manually identified horizontal resistance level (your call)
    vol_spike_mult : current 5-min bar volume must exceed this multiple of the
                     recent average 5-min volume to count as a "spike"
    """
    compression = is_compressing(daily_df, lookback=lookback)

    last_bar = intraday_5m_df.iloc[-1]
    avg_5m_vol = intraday_5m_df["volume"].iloc[-lookback:-1].mean()
    vol_spike = last_bar["volume"] >= (avg_5m_vol * vol_spike_mult)

    breakout = last_bar["close"] > key_resistance

    triggered = compression["is_compressing"] and breakout and vol_spike

    return {
        "triggered": triggered,
        "compression": compression,
        "breakout": breakout,
        "vol_spike": vol_spike,
        "last_close": round(last_bar["close"], 2),
        "key_resistance": key_resistance,
        "stop_loss": round(intraday_5m_df["low"].min(), 2),  # low of day
    }


# ---------------------------------------------------------------------------
# 4. Setup 2 -- Undercut and Rally (UNR)
# ---------------------------------------------------------------------------

def check_undercut_rally(intraday_df: pd.DataFrame, key_support: float,
                          vol_confirm_mult=1.2, lookback=10) -> dict:
    """
    key_support : manually identified base-support level (your call)
    Looks for a bar breaking below key_support, followed by a later bar
    reclaiming (closing back above) key_support, with volume confirming
    the reclaim bar.
    """
    recent = intraday_df.iloc[-lookback:]
    avg_vol = recent["volume"].iloc[:-1].mean()

    undercut_occurred = (recent["low"] < key_support).any()

    last_bar = recent.iloc[-1]
    reclaimed = last_bar["close"] > key_support
    vol_confirms = last_bar["volume"] >= (avg_vol * vol_confirm_mult)

    triggered = undercut_occurred and reclaimed and vol_confirms

    return {
        "triggered": triggered,
        "undercut_occurred": undercut_occurred,
        "reclaimed": reclaimed,
        "vol_confirms": vol_confirms,
        "last_close": round(last_bar["close"], 2),
        "key_support": key_support,
        "stop_loss": round(intraday_df["low"].min(), 2),  # low of day
    }


# ---------------------------------------------------------------------------
# 5. Setup 3 -- 30-Minute Pivot Entry
# ---------------------------------------------------------------------------

def check_30min_pivot(intraday_30m_df: pd.DataFrame, key_level: float,
                       near_level_pct=1.0) -> dict:
    """
    key_level : the EMA/support/gap level you're watching for a reversal at
                (your call, per-ticker)
    Pattern: a red 30-min candle down into key_level, then the first green
    30-min candle off that level, then entry on the NEXT 30-min candle
    breaking above that green candle's high.
    Needs at least 3 completed 30-min bars: [red_bar, green_candle, current_bar]
    """
    if len(intraday_30m_df) < 3:
        return {"triggered": False, "reason": "not enough 30-min bars yet"}

    bars = intraday_30m_df.iloc[-3:]
    two_ago, green_candle, current = bars.iloc[0], bars.iloc[1], bars.iloc[2]

    was_red = two_ago["close"] < two_ago["open"]
    is_green = green_candle["close"] > green_candle["open"]
    near_key_level = abs(green_candle["low"] - key_level) / key_level * 100 <= near_level_pct

    breaks_green_high = current["close"] > green_candle["high"] or current["high"] > green_candle["high"]

    triggered = was_red and is_green and near_key_level and breaks_green_high

    return {
        "triggered": triggered,
        "was_red_before": was_red,
        "green_candle_off_level": is_green,
        "near_key_level": near_key_level,
        "breaks_green_high": breaks_green_high,
        "key_level": key_level,
        "green_candle_high": round(green_candle["high"], 2),
        "stop_loss": round(green_candle["low"], 2),  # low of the green candle
    }


# ---------------------------------------------------------------------------
# 6. Institutional Flow Signal -- extreme RVOL + confirmation filters
#    (see the discussion of why raw RVOL alone is unreliable: halts, block
#    trades, low-float spikes, and climax/exhaustion volume all produce high
#    RVOL without real accumulation behind them)
# ---------------------------------------------------------------------------

def strong_close(bar, threshold_pct=75) -> bool:
    """
    True if the bar's close sits in the top `threshold_pct`% of its own
    high-low range -- i.e. buyers absorbed selling and held the bar near its
    high, rather than spiking and fading.
    """
    bar_range = bar["high"] - bar["low"]
    if bar_range == 0:
        return bar["close"] >= bar["open"]  # degenerate case: flat bar
    close_position_pct = (bar["close"] - bar["low"]) / bar_range * 100
    return close_position_pct >= threshold_pct


def sustained_volume(intraday_df: pd.DataFrame, bars=2, mult=1.3, baseline_window=10) -> dict:
    """
    True if the last `bars` bars ALL show volume >= mult * the average volume
    of the `baseline_window` bars before them -- distinguishes a real shift in
    participation from a single-bar spike that immediately reverts.
    """
    if len(intraday_df) < bars + baseline_window:
        return {"sustained": False, "reason": "not enough bars"}

    baseline = intraday_df["volume"].iloc[-(bars + baseline_window):-bars].mean()
    recent_bars = intraday_df["volume"].iloc[-bars:]
    all_elevated = (recent_bars >= baseline * mult).all()

    return {
        "sustained": bool(all_elevated),
        "baseline_vol": round(baseline, 0),
        "recent_vols": [round(v, 0) for v in recent_bars.tolist()],
    }


def making_fresh_high(intraday_df: pd.DataFrame) -> bool:
    """True if the current bar's high is the session high so far (confirms the
    volume is directional, not just churn within an existing range)."""
    return intraday_df["high"].iloc[-1] >= intraday_df["high"].max()


def institutional_flow_signal(intraday_df: pd.DataFrame, daily_avg_vol: float,
                               rvol_threshold=40, close_strength_pct=75,
                               sustained_bars=2, sustained_mult=1.3,
                               session_start="09:15", session_end="15:30",
                               tz="Asia/Kolkata") -> dict:
    """
    Composite signal: extreme RVOL + strong close + sustained (not one-bar)
    volume + a fresh session high. All four must hold -- this is deliberately
    stricter than "RVOL > threshold" alone, per the false-positive modes
    (halts, block trades, low-float spikes, climax volume) that raw RVOL
    doesn't distinguish between.

    NOTE: this does NOT check for a news/announcement catalyst -- that's a
    separate, market-specific lookup (see catalyst_nse.py / catalyst_us.py)
    that should be combined with this signal by the caller.
    """
    rvol = relative_volume(intraday_df, daily_avg_vol,
                            session_start=session_start, session_end=session_end, tz=tz)
    last_bar = intraday_df.iloc[-1]

    extreme_rvol = rvol["rvol_ratio"] >= rvol_threshold
    close_strong = strong_close(last_bar, threshold_pct=close_strength_pct)
    vol_sustained = sustained_volume(intraday_df, bars=sustained_bars, mult=sustained_mult)
    fresh_high = making_fresh_high(intraday_df)

    triggered = extreme_rvol and close_strong and vol_sustained.get("sustained", False) and fresh_high

    return {
        "triggered": triggered,
        "rvol": rvol,
        "extreme_rvol": extreme_rvol,
        "close_strong": close_strong,
        "volume_sustained": vol_sustained,
        "fresh_high": fresh_high,
        "last_close": round(last_bar["close"], 2),
    }
