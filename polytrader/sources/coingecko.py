from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx


COINGECKO = "https://api.coingecko.com/api/v3"


@dataclass(frozen=True)
class CgPriceSignal:
    symbol: str
    price_usd: float
    change_24h: float | None
    volume_24h_usd: float | None
    market_cap_usd: float | None
    ts: datetime
    source: str = "coingecko"


class CoinGeckoClient:
    """Minimal CoinGecko client.

    CoinGecko has both free and paid tiers; these endpoints typically work without an API key,
    but are subject to rate limits.
    """

    def __init__(self):
        self._client = httpx.AsyncClient(base_url=COINGECKO, timeout=20.0)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def simple_price(self, ids: list[str]) -> dict[str, Any]:
        r = await self._client.get(
            "/simple/price",
            params={
                "ids": ",".join(ids),
                "vs_currencies": "usd",
                "include_24hr_change": "true",
                "include_24hr_vol": "true",
                "include_market_cap": "true",
            },
        )
        r.raise_for_status()
        return r.json()


async def price_signal_for_ids(client: CoinGeckoClient, ids: list[str]) -> list[CgPriceSignal]:
    data = await client.simple_price(ids)
    ts = datetime.now(timezone.utc)
    out: list[CgPriceSignal] = []
    for coin_id, row in data.items():
        if not isinstance(row, dict):
            continue
        price = row.get("usd")
        if not isinstance(price, (int, float)):
            continue
        out.append(
            CgPriceSignal(
                symbol=coin_id,
                price_usd=float(price),
                change_24h=(float(row["usd_24h_change"]) if isinstance(row.get("usd_24h_change"), (int, float)) else None),
                volume_24h_usd=(float(row["usd_24h_vol"]) if isinstance(row.get("usd_24h_vol"), (int, float)) else None),
                market_cap_usd=(float(row["usd_market_cap"]) if isinstance(row.get("usd_market_cap"), (int, float)) else None),
                ts=ts,
            )
        )
    return out
