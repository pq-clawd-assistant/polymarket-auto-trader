from __future__ import annotations

from datetime import datetime, timezone

from polytrader.adapters.exchange import Exchange
from polytrader.core.types import Fill, Market, MarketQuote, Order


class PaperExchange(Exchange):
    """A stub exchange used for end-to-end testing.

    Replace list_markets/get_quotes with real Polymarket adapters once API details are known.
    """

    def __init__(self):
        self._markets = [
            Market(id="demo-1", question="Will it rain tomorrow?", category="weather", close_time=None),
            Market(id="demo-2", question="Will Team A win?", category="sports", close_time=None),
        ]
        self._quotes = {
            "demo-1": MarketQuote(market_id="demo-1", yes_price=0.40, no_price=0.60, liquidity_usd=1000),
            "demo-2": MarketQuote(market_id="demo-2", yes_price=0.55, no_price=0.45, liquidity_usd=500),
        }

    async def list_markets(self, limit: int) -> list[Market]:
        return self._markets[:limit]

    async def get_quotes(self, market_ids: list[str]) -> list[MarketQuote]:
        return [self._quotes[m] for m in market_ids if m in self._quotes]

    async def place_order(self, order: Order) -> Fill:
        # Naive fill at current quote.
        q = self._quotes[order.market_id]
        price = q.yes_price if order.side == "YES" else q.no_price
        return Fill(order=order, filled_fraction=order.fraction_of_bankroll, avg_price=price, ts=datetime.now(timezone.utc))
