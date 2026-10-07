"""Strategy registry.

Every strategy is a function `signals(df, params) -> pd.Series` that returns
"buy", "sell" or "hold" for every row of a daily OHLCV DataFrame. The live bot
reads the last value; the backtester walks the whole series.

To add a strategy: create a module with a `signals` function, import it here,
add it to STRATEGIES, and give it a params block in config.json.
"""

from . import bollinger, breakout, ma_crossover, macd, rsi

STRATEGIES = {
    "ma_crossover": ma_crossover.signals,
    "rsi": rsi.signals,
    "breakout": breakout.signals,
    "bollinger": bollinger.signals,
    "macd": macd.signals,
}


def combine(votes, mode):
    """Merge per-strategy votes into one action.

    any:      trade if at least one strategy fires and none disagree
    majority: trade if more than half of the strategies agree
    all:      trade only if every strategy agrees
    """
    n = len(votes)
    buys = sum(v == "buy" for v in votes.values())
    sells = sum(v == "sell" for v in votes.values())

    if mode == "any":
        if buys and not sells:
            return "buy"
        if sells and not buys:
            return "sell"
    elif mode == "majority":
        if buys > n / 2:
            return "buy"
        if sells > n / 2:
            return "sell"
    elif mode == "all":
        if buys == n:
            return "buy"
        if sells == n:
            return "sell"
    else:
        raise ValueError(f"Unknown combine mode: {mode}")
    return "hold"
