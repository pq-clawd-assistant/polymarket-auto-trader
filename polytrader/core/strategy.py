from __future__ import annotations

from dataclasses import dataclass

from polytrader.core.risk import clamp, kelly_fraction
from polytrader.core.types import FairValue, Market, MarketQuote, Opportunity


@dataclass
class StrategyParams:
    min_edge: float
    max_position_fraction: float
    kelly_fraction: float
    min_liquidity_usd: float


def find_opportunity(market: Market, quote: MarketQuote, fv: FairValue, p: StrategyParams) -> Opportunity | None:
    # liquidity gate
    if quote.liquidity_usd is not None and quote.liquidity_usd < p.min_liquidity_usd:
        return None

    # decide side
    implied_yes = quote.yes_price
    implied_no = quote.no_price

    # Edge definition: fv - implied (for YES), (1-fv) - implied_no (for NO)
    edge_yes = fv.p_yes - implied_yes
    edge_no = (1 - fv.p_yes) - implied_no

    if edge_yes <= edge_no:
        side = "NO"
        edge = edge_no
        price = implied_no
        p_side = 1 - fv.p_yes
    else:
        side = "YES"
        edge = edge_yes
        price = implied_yes
        p_side = fv.p_yes

    if edge < p.min_edge:
        return None

    raw_kelly = kelly_fraction(p_side, price)
    sized = clamp(raw_kelly * p.kelly_fraction, 0.0, p.max_position_fraction)

    return Opportunity(
        market=market,
        quote=quote,
        fv=fv,
        side=side,  # type: ignore
        edge=edge,
        suggested_fraction=sized,
    )
