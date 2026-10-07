"""Claude reviews each proposed trade and can approve it or veto it.

The AI can only confirm or block what the strategies propose; it never
originates trades and never overrides the risk limits in bot.py. Any error,
refusal or unparseable answer is treated as a veto.
"""

import logging
from typing import Literal

import anthropic
from pydantic import BaseModel

log = logging.getLogger("bot")

SYSTEM_PROMPT = """You review trade signals from a rule-based stock trading bot running on a paper trading account.

You receive a proposed action (buy or sell) for one stock, the votes of each technical strategy, recent daily prices, indicator values, the current position and recent news headlines.

Decide whether to approve the proposed action or hold instead. Approve only when the price action, indicators and news are consistent with the proposed trade. Return hold when signals conflict, when news suggests elevated event risk (earnings within days, lawsuits, guidance cuts, major macro events), or when the evidence is weak. Never return the opposite action of the one proposed: your choices are the proposed action or hold.

Keep the reasoning to two or three sentences that cite the specific data you relied on."""


class AIDecision(BaseModel):
    action: Literal["buy", "sell", "hold"]
    confidence: int  # 0-100
    reasoning: str


def _format_prompt(symbol, proposed, votes, df, position_qty, headlines):
    closes = df["Close"].tail(30)
    price_lines = "\n".join(f"{d.date()}: {c:.2f}" for d, c in closes.items())
    vote_lines = "\n".join(f"- {name}: {vote}" for name, vote in votes.items())
    news_lines = "\n".join(f"- {h}" for h in headlines) or "- (no recent headlines)"
    return f"""Symbol: {symbol}
Proposed action: {proposed}
Current position: {position_qty:g} shares

Strategy votes:
{vote_lines}

Last 30 daily closes:
{price_lines}

20-day average: {df["Close"].tail(20).mean():.2f}
50-day average: {df["Close"].tail(50).mean():.2f}

Recent news headlines:
{news_lines}"""


def fetch_headlines(news_client, symbol, limit):
    if news_client is None or limit <= 0:
        return []
    from alpaca.data.requests import NewsRequest

    try:
        news = news_client.get_news(NewsRequest(symbols=symbol, limit=limit))
        return [f"{a.created_at:%Y-%m-%d} {a.headline}" for a in news.data.get("news", [])]
    except Exception as e:
        log.warning("Could not fetch news for %s: %s", symbol, e)
        return []


def review_trade(client, ai_config, symbol, proposed, votes, df, position_qty, headlines):
    """Return an AIDecision, or None if the review failed (caller treats None as a veto)."""
    try:
        response = client.messages.parse(
            model=ai_config["model"],
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _format_prompt(symbol, proposed, votes, df, position_qty, headlines)}],
            output_config={"effort": ai_config.get("effort", "medium")},
            output_format=AIDecision,
        )
    except anthropic.APIStatusError as e:
        log.error("AI review failed for %s (HTTP %s): %s", symbol, e.status_code, e.message)
        return None
    except anthropic.APIConnectionError as e:
        log.error("AI review failed for %s (network): %s", symbol, e)
        return None

    if response.stop_reason == "refusal" or response.parsed_output is None:
        log.warning("AI gave no usable answer for %s (stop_reason=%s)", symbol, response.stop_reason)
        return None
    return response.parsed_output
