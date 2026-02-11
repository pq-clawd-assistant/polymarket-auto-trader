from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx


BINANCE = "https://api.binance.com"


@dataclass(frozen=True)
class Candle:
    open_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class BinanceClient:
    """Free public Binance market data client (no auth).

    Used only as an external price feed for crypto short-horizon models.
    """

    def __init__(self):
        self._client = httpx.AsyncClient(base_url=BINANCE, timeout=20.0)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def klines(self, *, symbol: str, interval: str, limit: int = 100) -> list[list[Any]]:
        r = await self._client.get(
            "/api/v3/klines",
            params={
                "symbol": symbol,
                "interval": interval,
                "limit": str(limit),
            },
        )
        r.raise_for_status()
        j = r.json()
        return j if isinstance(j, list) else []


def parse_klines(rows: list[list[Any]]) -> list[Candle]:
    out: list[Candle] = []
    for row in rows:
        if not (isinstance(row, list) and len(row) >= 6):
            continue
        try:
            ot = datetime.fromtimestamp(float(row[0]) / 1000.0, tz=timezone.utc)
            o = float(row[1])
            h = float(row[2])
            l = float(row[3])
            c = float(row[4])
            v = float(row[5])
        except Exception:
            continue
        if all(math.isfinite(x) for x in (o, h, l, c)) and c > 0:
            out.append(Candle(open_time=ot, open=o, high=h, low=l, close=c, volume=v))
    return out


def realized_vol_from_closes(closes: list[float], periods_per_year: float) -> float | None:
    if len(closes) < 3:
        return None
    rets: list[float] = []
    for a, b in zip(closes, closes[1:]):
        if a <= 0 or b <= 0:
            continue
        rets.append(math.log(b / a))
    if len(rets) < 2:
        return None
    m = sum(rets) / len(rets)
    var = sum((r - m) ** 2 for r in rets) / (len(rets) - 1)
    if var <= 0:
        return None
    return math.sqrt(var) * math.sqrt(periods_per_year)
