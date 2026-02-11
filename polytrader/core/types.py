from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal


Side = Literal["YES", "NO"]


@dataclass(frozen=True)
class Market:
    id: str
    question: str
    category: str | None
    start_time: datetime | None = None
    close_time: datetime | None = None
    outcomes: tuple[str, ...] = ("YES", "NO")


@dataclass(frozen=True)
class MarketQuote:
    market_id: str
    yes_price: float  # implied probability in [0,1]
    no_price: float
    liquidity_usd: float | None = None
    ts: datetime | None = None


@dataclass(frozen=True)
class FairValue:
    market_id: str
    p_yes: float
    confidence: float  # 0..1 (model-dependent)
    rationale: str | None = None


@dataclass(frozen=True)
class Opportunity:
    market: Market
    quote: MarketQuote
    fv: FairValue
    side: Side
    edge: float
    suggested_fraction: float


@dataclass(frozen=True)
class Order:
    market_id: str
    side: Side
    fraction_of_bankroll: float
    limit_price: float | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class Fill:
    order: Order
    filled_fraction: float
    avg_price: float
    ts: datetime
