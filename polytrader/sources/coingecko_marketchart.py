from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx


COINGECKO = "https://api.coingecko.com/api/v3"


@dataclass(frozen=True)
class MarketChart:
    coin_id: str
    vs: str
    days: int
    prices: list[tuple[datetime, float]]  # (ts, price)
    ts: datetime
    source: str = "coingecko"


class CoinGeckoMarketChartClient:
    def __init__(self):
        self._client = httpx.AsyncClient(base_url=COINGECKO, timeout=30.0)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def market_chart(self, coin_id: str, *, vs_currency: str = "usd", days: int = 30) -> dict[str, Any]:
        r = await self._client.get(
            f"/coins/{coin_id}/market_chart",
            params={
                "vs_currency": vs_currency,
                "days": str(days),
                "interval": "hourly" if days <= 90 else "daily",
            },
        )
        r.raise_for_status()
        return r.json()


def parse_market_chart(coin_id: str, vs: str, days: int, j: dict[str, Any]) -> MarketChart:
    prices_raw = j.get("prices")
    out: list[tuple[datetime, float]] = []
    if isinstance(prices_raw, list):
        for row in prices_raw:
            if not (isinstance(row, list) and len(row) >= 2):
                continue
            try:
                # ms epoch
                ts = datetime.fromtimestamp(float(row[0]) / 1000.0, tz=timezone.utc)
                px = float(row[1])
            except Exception:
                continue
            if math.isfinite(px) and px > 0:
                out.append((ts, px))
    return MarketChart(coin_id=coin_id, vs=vs, days=days, prices=out, ts=datetime.now(timezone.utc))


def realized_vol_annualized(prices: list[float], *, periods_per_year: float) -> float | None:
    """Realized volatility from log returns."""
    if len(prices) < 3:
        return None
    rets: list[float] = []
    for a, b in zip(prices, prices[1:]):
        if a <= 0 or b <= 0:
            continue
        rets.append(math.log(b / a))
    if len(rets) < 2:
        return None
    m = sum(rets) / len(rets)
    var = sum((r - m) ** 2 for r in rets) / (len(rets) - 1)
    if var < 0:
        return None
    return math.sqrt(var) * math.sqrt(periods_per_year)
