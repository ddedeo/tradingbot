import pandas as pd


def to_signals(index, buy, sell):
    """Turn boolean buy/sell masks into a "buy"/"sell"/"hold" Series."""
    out = pd.Series("hold", index=index)
    out[buy.fillna(False).astype(bool)] = "buy"
    out[sell.fillna(False).astype(bool)] = "sell"
    return out
