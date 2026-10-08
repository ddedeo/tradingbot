# Multi-Strategy Trading Bot

Trades an Alpaca **paper** account. Several technical strategies vote, the votes are combined,
hard risk limits are applied, and (optionally) Claude reviews each trade before it is placed.

```
prices (yfinance) -> strategies vote -> combine -> position & risk guards -> AI review -> order
```

## Setup

```bash
pip install -r requirements.txt
copy .env.example .env      # then fill in your keys
```

`.env` needs your Alpaca paper keys, plus `ANTHROPIC_API_KEY` if the AI reviewer is enabled.

## Commands

```bash
python backtest.py            # how each strategy would have done historically
python bot.py --dry-run       # evaluate today's signals, never trade
python bot.py                 # evaluate and trade
python bot.py --no-ai         # trade without the AI review step
python status.py              # display status report of every owned stock
```

Logs go to `logs/bot.log`. Create a file named `STOP` in this folder to halt all trading.

## Strategies

| Name | Buy | Sell |
|---|---|---|
| `ma_crossover` | short MA crosses above long MA | crosses below |
| `rsi` | RSI climbs back above oversold | RSI falls back below overbought |
| `breakout` | first close above the prior N-day high | first close below the prior N-day low |
| `bollinger` | close drops below the lower band | close rises above the upper band |

Add one by creating `strategies/<name>.py` with a `signals(df, params)` function that returns a
"buy"/"sell"/"hold" Series, registering it in `strategies/__init__.py`, and adding its params to `config.json`.

## Config (`config.json`)

| Key | Meaning |
|---|---|
| `symbols` | Stocks to watch |
| `strategies` | Which strategies run, with their parameters. Remove a block to disable it |
| `combine` | `any` (one fires, none disagree), `majority` (more than half agree), `all` (every one agrees) |
| `trade_size` | Shares per order |
| `lookback_days` | Calendar days of history used for live signals |
| `risk.max_positions` | Max open positions across the whole account |
| `risk.max_position_value` | Max $ for a single buy |
| `risk.max_daily_loss` | If today's loss reaches this, no new buys |
| `ai.enabled` | Have Claude approve or veto each trade |
| `ai.model` / `ai.effort` | Claude model and reasoning effort |
| `backtest_years` | History length for `backtest.py` |

## How the AI fits in

The AI only **confirms or blocks** trades the strategies propose. It sees the votes, the last 30
closes, moving averages, your position and recent Alpaca news headlines. It cannot start trades on
its own or override the risk limits, and any error or unclear answer counts as a veto.

## Guards

- No buy if you already hold the symbol; no sell if you hold less than `trade_size` (never shorts).
- During market hours today's unfinished bar is ignored, so signals use final closes.
- Orders are DAY market orders. Submitted after the close, they fill at the next open.

## Scheduling (Windows)

`run_bot.bat` runs the bot once. To run it every weekday at 4:15 PM local time:

```bash
schtasks /Create /TN "TradingBot" /TR "\"%CD%\run_bot.bat\"" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 16:15
```

Pick a time after the US close (4:00 PM New York) in your timezone. Remove it with `schtasks /Delete /TN "TradingBot" /F`.
