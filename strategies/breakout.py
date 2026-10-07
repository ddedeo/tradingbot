"""Buy on the first close above the prior N-day high; sell on the first close below the prior N-day low."""

from ._util import to_signals


def signals(df, params):
    close = df["Close"]
    n = params["lookback"]
    prior_high = close.rolling(n).max().shift(1)
    prior_low = close.rolling(n).min().shift(1)

    above = close > prior_high
    below = close < prior_low
    buy = above & ~above.shift(1, fill_value=False)
    sell = below & ~below.shift(1, fill_value=False)
    return to_signals(df.index, buy, sell)
