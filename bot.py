"""Multi-strategy trading bot for an Alpaca paper trading account.

Usage:
    python bot.py            # evaluate every symbol and trade on signals
    python bot.py --dry-run  # evaluate and log, but never place orders
    python bot.py --no-ai    # skip the AI review step

Create a file named STOP in this folder to halt all trading (kill switch).
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from ai_advisor import fetch_headlines, review_trade
from data import fetch_history
from strategies import STRATEGIES, combine

BASE_DIR = Path(__file__).resolve().parent
log = logging.getLogger("bot")


def setup_logging():
    (BASE_DIR / "logs").mkdir(exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S")
    file_handler = logging.FileHandler(BASE_DIR / "logs" / "bot.log", encoding="utf-8")
    file_handler.setFormatter(fmt)
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    log.setLevel(logging.INFO)
    log.addHandler(file_handler)
    log.addHandler(console)


def load_config():
    with open(BASE_DIR / "config.json") as f:
        config = json.load(f)
    unknown = set(config["strategies"]) - set(STRATEGIES)
    if unknown:
        sys.exit(f"config error: unknown strategies {sorted(unknown)}; available: {sorted(STRATEGIES)}")
    return config


def make_alpaca_clients(required):
    key, secret = os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY")
    if not key or not secret or key.startswith("your_"):
        if required:
            sys.exit("Missing ALPACA_API_KEY / ALPACA_SECRET_KEY in .env")
        return None, None
    from alpaca.data.historical.news import NewsClient
    from alpaca.trading.client import TradingClient

    return TradingClient(key, secret, paper=True), NewsClient(key, secret)


def make_ai_client(required):
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key or key.startswith("your_"):
        if required:
            sys.exit('Missing ANTHROPIC_API_KEY in .env (or set "ai": {"enabled": false} in config.json, or pass --no-ai)')
        return None
    import anthropic

    return anthropic.Anthropic()


def place_order(trading, symbol, qty, action):
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.trading.requests import MarketOrderRequest

    side = OrderSide.BUY if action == "buy" else OrderSide.SELL
    order = trading.submit_order(
        MarketOrderRequest(symbol=symbol, qty=qty, side=side, time_in_force=TimeInForce.DAY)
    )
    log.info("ORDER %s %s %s: id=%s status=%s", action.upper(), qty, symbol, order.id, order.status.value)


def main():
    parser = argparse.ArgumentParser(description="Multi-strategy trading bot")
    parser.add_argument("--dry-run", action="store_true", help="never place orders")
    parser.add_argument("--no-ai", action="store_true", help="skip the AI review step")
    args = parser.parse_args()

    setup_logging()
    if (BASE_DIR / "STOP").exists():
        log.warning("STOP file present: kill switch active, exiting without trading.")
        return

    load_dotenv(BASE_DIR / ".env")
    config = load_config()
    risk = config["risk"]
    qty = config["trade_size"]
    use_ai = config["ai"]["enabled"] and not args.no_ai

    trading, news = make_alpaca_clients(required=not args.dry_run)
    ai_client = make_ai_client(required=use_ai and not args.dry_run) if use_ai else None
    if use_ai and ai_client is None:
        log.info("Dry run without ANTHROPIC_API_KEY: AI review will be skipped.")

    log.info("=== Run start (%s) ===", "DRY RUN" if args.dry_run else "LIVE PAPER")

    positions, buys_blocked = {}, False
    if trading:
        account = trading.get_account()
        daily_pnl = float(account.equity) - float(account.last_equity)
        positions = {p.symbol: float(p.qty) for p in trading.get_all_positions()}
        log.info("Equity $%s, today's P/L $%.2f, open positions: %s",
                 account.equity, daily_pnl, positions or "none")
        if daily_pnl <= -risk["max_daily_loss"]:
            buys_blocked = True
            log.warning("Daily loss limit hit ($%.2f): no new buys today.", daily_pnl)
    else:
        log.info("No Alpaca keys: assuming no open positions.")

    for symbol in config["symbols"]:
        try:
            df = fetch_history(symbol, config["lookback_days"])
        except Exception as e:
            log.error("%s: could not load prices: %s", symbol, e)
            continue

        votes = {name: STRATEGIES[name](df, params).iloc[-1] for name, params in config["strategies"].items()}
        action = combine(votes, config["combine"])
        price = df["Close"].iloc[-1]
        held = positions.get(symbol, 0.0)
        log.info("%s close %.2f (%s) votes=%s -> %s", symbol, price, df.index[-1].date(), votes, action.upper())

        if action == "hold":
            continue

        # Position and risk guards (the AI cannot override these).
        if action == "buy":
            if held > 0:
                log.info("%s: already holding %g, skipping buy.", symbol, held)
                continue
            if buys_blocked:
                log.info("%s: daily loss limit active, skipping buy.", symbol)
                continue
            if len(positions) >= risk["max_positions"]:
                log.info("%s: at max_positions (%d), skipping buy.", symbol, risk["max_positions"])
                continue
            if price * qty > risk["max_position_value"]:
                log.info("%s: $%.2f exceeds max_position_value $%d, skipping buy.",
                         symbol, price * qty, risk["max_position_value"])
                continue
        elif held < qty:
            log.info("%s: holding %g (< trade size %d), skipping sell.", symbol, held, qty)
            continue

        if ai_client:
            headlines = fetch_headlines(news, symbol, config["ai"].get("news_headlines", 10))
            decision = review_trade(ai_client, config["ai"], symbol, action, votes, df, held, headlines)
            if decision is None or decision.action != action:
                verdict = decision.action if decision else "no answer"
                log.info("%s: AI VETO (%s). %s", symbol, verdict, decision.reasoning if decision else "")
                continue
            log.info("%s: AI APPROVED (confidence %d). %s", symbol, decision.confidence, decision.reasoning)

        if args.dry_run:
            log.info("%s: DRY RUN, would %s %d shares.", symbol, action.upper(), qty)
            continue

        place_order(trading, symbol, qty, action)
        if action == "buy":
            positions[symbol] = qty
        else:
            positions.pop(symbol, None)

    log.info("=== Run end ===")


if __name__ == "__main__":
    main()
