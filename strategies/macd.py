"""Buy when the MACD line crosses above its signal line; sell on the cross below.

MACD = fast EMA - slow EMA of the close. The signal line is an EMA of MACD itself,
so a cross means short-term momentum is turning relative to its recent trend.
"""

from ._util import to_signals


def signals(df, params):
    close = df["Close"]
    fast = close.ewm(span=params["fast"], adjust=False, min_periods=params["fast"]).mean()
    slow = close.ewm(span=params["slow"], adjust=False, min_periods=params["slow"]).mean()
    macd = fast - slow
    signal = macd.ewm(span=params["signal"], adjust=False, min_periods=params["signal"]).mean()

    buy = (macd.shift(1) <= signal.shift(1)) & (macd > signal)
    sell = (macd.shift(1) >= signal.shift(1)) & (macd < signal)
    return to_signals(df.index, buy, sell)
