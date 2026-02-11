from __future__ import annotations

from abc import ABC, abstractmethod

from polytrader.core.types import Fill, Market, MarketQuote, Order


class Exchange(ABC):
    @abstractmethod
    async def list_markets(self, limit: int) -> list[Market]:
        raise NotImplementedError

    @abstractmethod
    async def get_quotes(self, market_ids: list[str]) -> list[MarketQuote]:
        raise NotImplementedError

    @abstractmethod
    async def place_order(self, order: Order) -> Fill:
        raise NotImplementedError
