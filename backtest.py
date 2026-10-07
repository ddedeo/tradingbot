"""Replay every strategy (and the combined vote) over historical prices.

Usage:
    python backtest.py                    # symbols and years from config.json
    python backtest.py --years 5 --symbols MU NVDA

Rules: long-only, `trade_size` shares, signal on day N's close fills at day N+1's
open, no commissions or slippage. The AI reviewer is not included (it would make
one paid API call per historical signal), so treat results as the strategies' raw edge.
"""

import argparse
import json
from pathlib import Path

import pandas as pd

from data import fetch_history
from risk import regime_series
from strategies import STRATEGIES, combine

BASE_DIR = Path(__file__).resolve().parent


def simulate(df, signals, qty, trail_pct=None, regime=None):
    """regime: bool Series (True = buys allowed); trail_pct: trailing stop on closes."""
    opens, closes = df["Open"].to_numpy(), df["Close"].to_numpy()
    allowed = regime.reindex(df.index).ffill().fillna(False).to_numpy() if regime is not None else None
    position, entry, peak, realized = 0, 0.0, 0.0, 0.0
    stop_pending = False
    trades, equity, in_market = [], [], 0

    for i in range(len(df)):
        # Fill yesterday's signal (or stop) at today's open.
        if i > 0:
            sig = signals.iloc[i - 1]
            if position > 0 and (sig == "sell" or stop_pending):
                pnl = (opens[i] - entry) * position
                realized += pnl
                trades.append(pnl)
                position, stop_pending = 0, False
            elif sig == "buy" and position == 0 and (allowed is None or allowed[i - 1]):
                position, entry, peak = qty, opens[i], opens[i]
        if position > 0:
            peak = max(peak, closes[i])
            if trail_pct and closes[i] <= peak * (1 - trail_pct / 100):
                stop_pending = True
        in_market += position > 0
        equity.append(realized + (closes[i] - entry) * position)

    if position > 0:  # mark the open trade at the last close
        trades.append((closes[-1] - entry) * position)

    equity = pd.Series(equity)
    return {
        "pnl": equity.iloc[-1],
        "trades": len(trades),
        "win_rate": (sum(t > 0 for t in trades) / len(trades) * 100) if trades else 0.0,
        "max_dd": (equity - equity.cummax()).min(),
        "exposure": in_market / len(df) * 100,
    }


def main():
    with open(BASE_DIR / "config.json") as f:
        config = json.load(f)

    parser = argparse.ArgumentParser(description="Backtest the configured strategies")
    parser.add_argument("--years", type=float, default=config.get("backtest_years", 3))
    parser.add_argument("--symbols", nargs="+", default=config["symbols"])
    args = parser.parse_args()

    qty = config["trade_size"]
    trail = config["risk"].get("trailing_stop_pct")
    rf = config.get("regime_filter", {})
    regime = None
    if rf.get("enabled"):
        spy = fetch_history(rf["symbol"], int(args.years * 365) + int(rf["ma_days"] * 1.6) + 30)
        regime = regime_series(spy, rf["ma_days"])

    for symbol in args.symbols:
        df = fetch_history(symbol, int(args.years * 365))
        all_signals = {name: STRATEGIES[name](df, params) for name, params in config["strategies"].items()}
        combined = pd.DataFrame(all_signals).apply(lambda row: combine(row.to_dict(), config["combine"]), axis=1)
        label = f"combined ({config['combine']})"

        runs = [(name, signals, {}) for name, signals in all_signals.items()]
        runs.append((label, combined, {}))
        if trail:
            runs.append((f"  + {trail:g}% trail stop", combined, {"trail_pct": trail}))
        if regime is not None:
            runs.append((f"  + {rf['symbol']} filter", combined, {"regime": regime}))
        if trail and regime is not None:
            runs.append(("  + both", combined, {"trail_pct": trail, "regime": regime}))

        buy_hold = (df["Close"].iloc[-1] - df["Open"].iloc[0]) * qty
        print(f"\n{symbol}  {df.index[0].date()} -> {df.index[-1].date()}  ({qty} share{'s' if qty != 1 else ''})")
        print(f"{'strategy':<24}{'P/L $':>11}{'trades':>8}{'win %':>8}{'max DD $':>11}{'in mkt %':>10}")
        for name, signals, opts in runs:
            r = simulate(df, signals, qty, **opts)
            print(f"{name:<24}{r['pnl']:>11.2f}{r['trades']:>8}{r['win_rate']:>8.0f}{r['max_dd']:>11.2f}{r['exposure']:>10.0f}")
        print(f"{'buy & hold':<24}{buy_hold:>11.2f}{1:>8}{'':>8}{'':>11}{100:>10}")


if __name__ == "__main__":
    main()
