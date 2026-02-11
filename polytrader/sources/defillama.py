from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx


DEFILLAMA = "https://api.llama.fi"


@dataclass(frozen=True)
class LlamaTvlSignal:
    key: str  # chain or protocol
    tvl_usd: float
    ts: datetime
    source: str = "defillama"


class DefiLlamaClient:
    def __init__(self):
        self._client = httpx.AsyncClient(base_url=DEFILLAMA, timeout=20.0)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def chains(self) -> list[dict[str, Any]]:
        r = await self._client.get("/v2/chains")
        r.raise_for_status()
        j = r.json()
        return j if isinstance(j, list) else []

    async def protocols(self) -> list[dict[str, Any]]:
        r = await self._client.get("/protocols")
        r.raise_for_status()
        j = r.json()
        return j if isinstance(j, list) else []

    async def stablecoins(self) -> dict[str, Any]:
        r = await self._client.get("/stablecoins")
        r.raise_for_status()
        return r.json()


async def top_chain_tvl(client: DefiLlamaClient, limit: int = 30) -> list[LlamaTvlSignal]:
    rows = await client.chains()
    ts = datetime.now(timezone.utc)
    out: list[LlamaTvlSignal] = []
    for row in rows[:limit]:
        name = row.get("name")
        tvl = row.get("tvl")
        if isinstance(name, str) and isinstance(tvl, (int, float)):
            out.append(LlamaTvlSignal(key=name, tvl_usd=float(tvl), ts=ts))
    return out
