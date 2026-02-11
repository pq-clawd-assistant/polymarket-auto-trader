from __future__ import annotations

from abc import ABC, abstractmethod

from polytrader.core.types import FairValue, Market


class FairValueModel(ABC):
    @abstractmethod
    async def estimate(self, market: Market) -> FairValue:
        raise NotImplementedError


class HeuristicBaseline(FairValueModel):
    """Very dumb baseline: returns 0.5 with low confidence.

    This is just a scaffold; you’ll plug in real signal models (NOAA, injuries, onchain, etc.)
    and/or an LLM *with structured inputs*.
    """

    async def estimate(self, market: Market) -> FairValue:
        return FairValue(market_id=market.id, p_yes=0.5, confidence=0.2, rationale="baseline")
