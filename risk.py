"""Rules that sit outside the strategy vote: the trailing stop and the market regime filter."""

import logging

import pandas as pd

from data import fetch_history

log = logging.getLogger("bot")


def regime_series(spy_df, ma_days):
    """True on days the index closed above its moving average (buys allowed)."""
    close = spy_df["Close"]
    ma = close.rolling(ma_days).mean()
    return (close > ma) & ma.notna()


def regime_allows_buys(rf_config):
    """Live check of the regime filter. Fails safe: if SPY can't be loaded, buys are blocked."""
    if not rf_config.get("enabled"):
        return True
    symbol, ma_days = rf_config["symbol"], rf_config["ma_days"]
    try:
        spy = fetch_history(symbol, int(ma_days * 1.6) + 30)  # ~1.45 calendar days per trading day
    except Exception as e:
        log.error("Regime filter: could not load %s (%s); blocking buys.", symbol, e)
        return False

    close = spy["Close"].iloc[-1]
    ma = spy["Close"].tail(ma_days).mean()
    allowed = bool(regime_series(spy, ma_days).iloc[-1])
    log.info("Regime filter: %s %.2f vs %d-day MA %.2f -> buys %s",
             symbol, close, ma_days, ma, "ALLOWED" if allowed else "BLOCKED")
    return allowed


def last_buy_fill(trading, symbol):
    """(fill time, fill price) of the most recent filled buy for symbol, or None."""
    from alpaca.trading.enums import OrderSide, QueryOrderStatus
    from alpaca.trading.requests import GetOrdersRequest

    orders = trading.get_orders(GetOrdersRequest(
        status=QueryOrderStatus.CLOSED, symbols=[symbol], side=OrderSide.BUY, limit=50))
    filled = [o for o in orders if o.filled_at and o.filled_avg_price]
    if not filled:
        return None
    latest = max(filled, key=lambda o: o.filled_at)
    return latest.filled_at, float(latest.filled_avg_price)


def trailing_stop_hit(trading, symbol, df, trail_pct):
    """True if the last close is trail_pct% or more below the highest close since the last buy."""
    fill = last_buy_fill(trading, symbol)
    if fill is None:
        log.warning("%s: no filled buy order found; trailing stop not applied.", symbol)
        return False
    filled_at, entry = fill

    since = pd.Timestamp(filled_at).tz_convert(df.index.tz).normalize()
    closes = df["Close"][df.index >= since]
    peak = max(entry, closes.max()) if not closes.empty else entry
    last = df["Close"].iloc[-1]
    drop = (peak - last) / peak * 100

    log.info("%s: trailing stop check: bought %.2f on %s, peak %.2f, now %.2f (%.1f%% below peak, stop at %g%%)",
             symbol, entry, since.date(), peak, last, drop, trail_pct)
    return drop >= trail_pct
