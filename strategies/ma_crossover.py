"""Buy when the short moving average crosses above the long one; sell on the cross below."""

from ._util import to_signals


def signals(df, params):
    close = df["Close"]
    short_ma = close.rolling(params["short_window"]).mean()
    long_ma = close.rolling(params["long_window"]).mean()

    buy = (short_ma.shift(1) <= long_ma.shift(1)) & (short_ma > long_ma)
    sell = (short_ma.shift(1) >= long_ma.shift(1)) & (short_ma < long_ma)
    return to_signals(df.index, buy, sell)
