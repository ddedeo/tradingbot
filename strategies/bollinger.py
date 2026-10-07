"""Mean reversion: buy when price drops below the lower band; sell when it rises above the upper band."""

from ._util import to_signals


def signals(df, params):
    close = df["Close"]
    mid = close.rolling(params["window"]).mean()
    std = close.rolling(params["window"]).std()
    lower = mid - params["num_std"] * std
    upper = mid + params["num_std"] * std

    buy = (close.shift(1) >= lower.shift(1)) & (close < lower)
    sell = (close.shift(1) <= upper.shift(1)) & (close > upper)
    return to_signals(df.index, buy, sell)
