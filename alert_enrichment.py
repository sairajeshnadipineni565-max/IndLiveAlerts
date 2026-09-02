"""
Shared alert-enrichment helpers: position sizing, target price, and a
candlestick snapshot image -- called by every scanner (main setups +
institutional flow, both markets) so alerts are actionable without
switching to a chart app.
"""

import io
import matplotlib
matplotlib.use("Agg")  # headless -- no display needed on the VM
import matplotlib.pyplot as plt
import matplotlib.dates as mdates


def compute_trade_plan(entry_price: float, stop_loss: float, account_capital: float,
                        risk_per_trade_pct: float, target_r_multiple: float) -> dict:
    """
    Position size from risk-per-share, and a target at target_r_multiple * R
    (R = entry-to-stop distance). Works for either direction, though these
    scanners are long-only.
    """
    risk_per_share = abs(entry_price - stop_loss)
    if risk_per_share <= 0:
        return {"valid": False, "reason": "entry equals stop -- can't size a trade"}

    risk_amount = account_capital * (risk_per_trade_pct / 100)
    quantity = int(risk_amount // risk_per_share)
    target_price = entry_price + (risk_per_share * target_r_multiple)

    return {
        "valid": quantity > 0,
        "entry": round(entry_price, 2),
        "stop_loss": round(stop_loss, 2),
        "target": round(target_price, 2),
        "risk_per_share": round(risk_per_share, 2),
        "risk_amount": round(risk_amount, 2),
        "quantity": quantity,
        "r_multiple": target_r_multiple,
    }


def format_trade_plan_line(plan: dict, currency_symbol="$") -> str:
    if not plan.get("valid"):
        return f"⚠️ Position sizing unavailable ({plan.get('reason', 'unknown')})"
    return (f"• *Entry:* `{currency_symbol}{plan['entry']}`  "
            f"*Stop:* `{currency_symbol}{plan['stop_loss']}`  "
            f"*Target ({plan['r_multiple']}R):* `{currency_symbol}{plan['target']}`\n"
            f"• *Qty:* `{plan['quantity']}`  "
            f"*Risk:* `{currency_symbol}{plan['risk_amount']}`")


def render_chart_snapshot(df, symbol: str, entry_price: float = None,
                           stop_loss: float = None, target: float = None,
                           key_level: float = None, lookback_bars: int = 40) -> bytes:
    """
    Renders the last `lookback_bars` candles as a PNG (returned as bytes,
    ready to POST to Telegram's sendPhoto). Marks entry/stop/target/key_level
    as horizontal lines where provided.
    """
    plot_df = df.iloc[-lookback_bars:].copy()

    fig, (ax_price, ax_vol) = plt.subplots(
        2, 1, figsize=(8, 5), sharex=True,
        gridspec_kw={"height_ratios": [3, 1]}, dpi=110,
    )

    # Candlesticks (manual, no extra dependency)
    for idx, row in enumerate(plot_df.itertuples()):
        color = "#26a69a" if row.close >= row.open else "#ef5350"
        ax_price.plot([idx, idx], [row.low, row.high], color=color, linewidth=1)
        ax_price.add_patch(plt.Rectangle(
            (idx - 0.3, min(row.open, row.close)), 0.6, max(abs(row.close - row.open), 0.0001),
            color=color,
        ))
        ax_vol.bar(idx, row.volume, color=color, width=0.6)

    def hline(value, color, label):
        if value is not None:
            ax_price.axhline(value, color=color, linestyle="--", linewidth=1, label=label)

    hline(entry_price, "#2962ff", "Entry")
    hline(stop_loss, "#ef5350", "Stop")
    hline(target, "#26a69a", "Target")
    hline(key_level, "#ff9800", "Key Level")

    ax_price.set_title(f"{symbol} -- last {lookback_bars} bars", fontsize=10)
    ax_price.legend(loc="upper left", fontsize=7, framealpha=0.5)
    ax_price.grid(alpha=0.2)
    ax_vol.grid(alpha=0.2)
    plt.setp(ax_price.get_xticklabels(), visible=False)
    ax_vol.set_xticks([])
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return buf.read()
