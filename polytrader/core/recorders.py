from __future__ import annotations

from datetime import datetime, timedelta, timezone

from polytrader.core.types import Market
from polytrader.sources.chainlink_streams import ChainlinkStreamsClient, latest_price
from polytrader.storage.sqlite import Store


BTC_USD_CHAINLINK_FEED_ID = "0x00039d9e45394f473ab1f050a1b963e6b05351e52d71e507509ada0c95ed75b8"


async def record_start_prices(markets: list[Market], *, tolerance_seconds: int = 10) -> int:
    """Record Chainlink stream price at the start of a market interval.

    We store (market_id, start_time_iso) -> price. This lets the BTC up/down model match settlement rules.

    This only works if the bot is running around the market start time.
    """

    store = Store()
    now = datetime.now(timezone.utc)

    candidates: list[Market] = []
    for m in markets:
        if not m.start_time:
            continue
        dt = abs((m.start_time - now).total_seconds())
        if dt <= tolerance_seconds:
            candidates.append(m)

    if not candidates:
        return 0

    cl = ChainlinkStreamsClient()
    try:
        live = await latest_price(cl, BTC_USD_CHAINLINK_FEED_ID)
    finally:
        await cl.aclose()

    if not live:
        return 0

    n = 0
    for m in candidates:
        start_iso = m.start_time.astimezone(timezone.utc).isoformat()
        if store.get_start_price(m.id, start_iso) is None:
            store.set_start_price(m.id, start_iso, live.price, source="chainlink live")
            n += 1

    return n
