"""Buy when RSI climbs back above the oversold level; sell when it falls back below overbought."""

from ._util import to_signals


def compute_rsi(close, period):
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = gain / loss
    return 100 - 100 / (1 + rs)


def signals(df, params):
    rsi = compute_rsi(df["Close"], params["period"])
    oversold, overbought = params["oversold"], params["overbought"]

    buy = (rsi.shift(1) < oversold) & (rsi >= oversold)
    sell = (rsi.shift(1) > overbought) & (rsi <= overbought)
    return to_signals(df.index, buy, sell)
