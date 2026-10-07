from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf


def fetch_history(symbol, days, completed_bars_only=True):
    """Daily OHLCV for the last `days` calendar days.

    With completed_bars_only, today's bar is dropped while the market is still
    open, so signals are based on final closes rather than a moving price.
    """
    end = datetime.now() + timedelta(days=1)
    start = end - timedelta(days=days)
    df = yf.Ticker(symbol).history(start=start, end=end, interval="1d")
    if df.empty:
        raise RuntimeError(f"No price data returned for {symbol}")

    if completed_bars_only:
        now = pd.Timestamp.now(tz="America/New_York")
        last = df.index[-1]
        if last.date() == now.date() and now.hour < 16:
            df = df.iloc[:-1]
    return df
