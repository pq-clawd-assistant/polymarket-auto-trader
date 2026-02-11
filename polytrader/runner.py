from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from rich.console import Console

from polytrader.adapters.paper import PaperExchange
from polytrader.adapters.polymarket_public import PolymarketPublicExchange
from polytrader.core.strategy import StrategyParams, find_opportunity
from polytrader.core.types import Order
from polytrader.models.router import RouterFairValueModel
from polytrader.settings import settings
from polytrader.storage.sqlite import Store


console = Console()


async def run_once() -> None:
    # Swap exchange adapter based on settings.exchange
    if settings.exchange == "polymarket-public":
        ex = PolymarketPublicExchange(user_agent=settings.nws_user_agent)
    else:
        ex = PaperExchange()
    model = RouterFairValueModel()
    store = Store()

    markets = await ex.list_markets(limit=settings.max_markets)
    quotes = await ex.get_quotes([m.id for m in markets])
    q_by_id = {q.market_id: q for q in quotes}

    params = StrategyParams(
        min_edge=settings.min_edge,
        max_position_fraction=settings.max_position_fraction,
        kelly_fraction=settings.kelly_fraction,
        min_liquidity_usd=settings.min_liquidity_usd,
    )

    opps = []
    for m in markets:
        q = q_by_id.get(m.id)
        if not q:
            continue
        fv = await model.estimate(m)
        opp = find_opportunity(m, q, fv, params)
        if opp:
            opps.append(opp)
            store.log_opportunity(opp)

    opps.sort(key=lambda o: o.edge, reverse=True)

    if not opps:
        console.log("No opportunities")
        return

    console.rule(f"Top opportunities ({len(opps)})")
    for opp in opps[:10]:
        console.log(
            f"{opp.market.id} {opp.side} edge={opp.edge:.3f} sized={opp.suggested_fraction:.3f} "
            f"implied_yes={opp.quote.yes_price:.3f} fv_yes={opp.fv.p_yes:.3f} ({opp.market.question})"
        )

    # Auto-execute only when the exchange supports it.
    if settings.mode == "paper" and settings.exchange == "paper":
        for opp in opps[:3]:
            if opp.suggested_fraction <= 0:
                continue
            order = Order(
                market_id=opp.market.id,
                side=opp.side,
                fraction_of_bankroll=opp.suggested_fraction,
                limit_price=None,
                created_at=datetime.now(timezone.utc),
            )
            fill = await ex.place_order(order)
            store.log_fill(fill)
            console.log(f"FILLED {fill.order.market_id} {fill.order.side} f={fill.filled_fraction:.3f} @ {fill.avg_price:.3f}")


async def run_forever() -> None:
    console.log(f"Starting runner: interval={settings.interval_seconds}s mode={settings.mode}")
    while True:
        try:
            await run_once()
        except Exception as e:
            console.log(f"ERROR: {e!r}")
        await asyncio.sleep(settings.interval_seconds)
