from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx


ALTME = "https://api.alternative.me"


@dataclass(frozen=True)
class FearGreedSignal:
    value: int  # 0..100
    value_classification: str
    ts: datetime
    source: str = "alternative.me"


class FearGreedClient:
    def __init__(self):
        self._client = httpx.AsyncClient(base_url=ALTME, timeout=20.0)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def latest(self) -> dict[str, Any]:
        r = await self._client.get("/fng/")
        r.raise_for_status()
        return r.json()


async def latest_fear_greed(client: FearGreedClient) -> FearGreedSignal | None:
    j = await client.latest()
    data = j.get("data")
    if not isinstance(data, list) or not data:
        return None
    row = data[0]
    try:
        value = int(row.get("value"))
        cls = str(row.get("value_classification"))
    except Exception:
        return None
    return FearGreedSignal(value=value, value_classification=cls, ts=datetime.now(timezone.utc))
