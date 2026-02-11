from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx


CHAINLINK_DATA = "https://data.chain.link"


@dataclass(frozen=True)
class StreamReport:
    feed_id: str
    valid_from: datetime
    price: float
    bid: float | None
    ask: float | None
    ts: datetime
    source: str = "data.chain.link (query-timescale)"


class ChainlinkStreamsClient:
    """Client for Chainlink Data Streams web endpoints used by data.chain.link.

    Observed endpoints:
    - /api/query-timescale?query=LIVE_STREAM_REPORTS_QUERY&variables={"feedId":"0x..."}

    Notes:
    - Some endpoints are more reliable if you send browser-like headers.
    - Prices are returned as large integers; empirically BTC/USD appears scaled by 1e18.
      (We treat values as 1e18 fixed-point unless otherwise configured.)
    """

    def __init__(
        self,
        *,
        scale: float = 1e18,
        user_agent: str = (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        referer: str = "https://data.chain.link/streams/btc-usd",
    ):
        self.scale = scale
        self._client = httpx.AsyncClient(
            base_url=CHAINLINK_DATA,
            timeout=20.0,
            headers={
                "User-Agent": user_agent,
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-GB,en;q=0.9,en-US;q=0.8",
                "Referer": referer,
                "Origin": "https://data.chain.link",
                "DNT": "1",
                "Connection": "keep-alive",
            },
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def live_stream_reports(self, feed_id: str, *, limit: int = 25) -> list[StreamReport]:
        variables = json.dumps({"feedId": feed_id})
        r = await self._client.get(
            "/api/query-timescale",
            params={
                "query": "LIVE_STREAM_REPORTS_QUERY",
                "variables": variables,
            },
        )
        r.raise_for_status()
        j = r.json()
        nodes = (((j.get("data") or {}).get("liveStreamReports") or {}).get("nodes"))
        if not isinstance(nodes, list):
            return []

        out: list[StreamReport] = []
        ts = datetime.now(timezone.utc)
        for row in nodes[:limit]:
            if not isinstance(row, dict):
                continue
            vts = row.get("validFromTimestamp")
            try:
                valid_from = datetime.fromisoformat(str(vts)).astimezone(timezone.utc)
            except Exception:
                continue

            def _fp(x: Any) -> float | None:
                try:
                    return float(int(str(x))) / self.scale
                except Exception:
                    return None

            price = _fp(row.get("price"))
            if price is None:
                continue
            bid = _fp(row.get("bid"))
            ask = _fp(row.get("ask"))
            out.append(
                StreamReport(
                    feed_id=feed_id,
                    valid_from=valid_from,
                    price=price,
                    bid=bid,
                    ask=ask,
                    ts=ts,
                )
            )
        return out


async def latest_price(client: ChainlinkStreamsClient, feed_id: str) -> StreamReport | None:
    rows = await client.live_stream_reports(feed_id, limit=1)
    return rows[0] if rows else None
