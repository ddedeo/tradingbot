"""Read-only report: every stock you own plus every stock the bot watches,
with each strategy's vote, the combined decision, P/L and trailing stop distance.

Usage:
    python status.py              # owned + watched stocks
    python status.py NVDA TSLA    # also check any extra symbols

Never places orders.
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from data import fetch_history
from risk import regime_allows_buys, trailing_stop_info
from strategies import STRATEGIES, combine

BASE_DIR = Path(__file__).resolve().parent


def main():
    load_dotenv(BASE_DIR / ".env")
    with open(BASE_DIR / "config.json") as f:
        config = json.load(f)

    from alpaca.trading.client import TradingClient

    trading = TradingClient(os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY"), paper=True)
    account = trading.get_account()
    positions = {p.symbol: p for p in trading.get_all_positions()}

    watched = config["symbols"]
    symbols = list(dict.fromkeys(list(positions) + watched + [s.upper() for s in sys.argv[1:]]))
    trail_pct = config["risk"].get("trailing_stop_pct")
    names = list(config["strategies"])

    print(f"\nAccount equity ${float(account.equity):,.2f}   cash ${float(account.cash):,.2f}   "
          f"today ${float(account.equity) - float(account.last_equity):+,.2f}")
    regime_ok = regime_allows_buys(config.get("regime_filter", {}))
    rf = config.get("regime_filter", {})
    if rf.get("enabled"):
        print(f"Market filter ({rf['symbol']} vs {rf['ma_days']}-day avg): buys {'ALLOWED' if regime_ok else 'BLOCKED'}")

    short = {"ma_crossover": "MA", "rsi": "RSI", "breakout": "BRK", "bollinger": "BOL", "macd": "MACD"}
    header = f"\n{'symbol':<7}{'own':>5}{'close':>10}{'P/L $':>10}{'P/L %':>8}  " + \
             "".join(f"{short.get(n, n[:5]):>6}" for n in names) + f"  {'DECISION':<9}{'managed':<9}trailing stop"
    print(header)
    print("-" * len(header))

    for symbol in symbols:
        try:
            df = fetch_history(symbol, config["lookback_days"])
        except Exception as e:
            print(f"{symbol:<7} could not load prices: {e}")
            continue

        votes = {n: STRATEGIES[n](df, config["strategies"][n]).iloc[-1] for n in names}
        decision = combine(votes, config["combine"]).upper()
        pos = positions.get(symbol)
        qty = float(pos.qty) if pos else 0
        pl = f"{float(pos.unrealized_pl):>10.2f}{float(pos.unrealized_plpc) * 100:>7.1f}%" if pos else f"{'':>10}{'':>8}"

        stop = ""
        if pos and trail_pct:
            info = trailing_stop_info(trading, symbol, df, trail_pct)
            if info:
                stop = f"sells below ${info['stop_price']:.2f} ({info['drop_pct']:.1f}% off peak ${info['peak']:.2f})"
            else:
                stop = "no buy order found"
        if symbol not in watched:
            stop = "not in config symbols: bot ignores it"

        managed = "yes" if symbol in watched else "no"
        vote_cols = "".join(f"{votes[n]:>6}" for n in names)
        print(f"{symbol:<7}{qty:>5g}{df['Close'].iloc[-1]:>10.2f}{pl}  {vote_cols}  {decision:<9}{managed:<9}{stop}")

    print(f"\nPrices are the last completed daily close. Combine mode: {config['combine']}. "
          "DECISION is what the strategies say before risk rules and AI review.")


if __name__ == "__main__":
    main()
