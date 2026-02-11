from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx


NWS_API = "https://api.weather.gov"


@dataclass(frozen=True)
class NwsPoint:
    lat: float
    lon: float


@dataclass(frozen=True)
class NwsPopSignal:
    """Probability-of-precipitation (PoP) style signal.

    p_rain is in [0,1].
    """

    p_rain: float
    window_start: datetime
    window_end: datetime
    source: str
    details: str | None = None


class NwsClient:
    """Minimal NWS API client.

    NWS requires a descriptive User-Agent header.
    See: https://www.weather.gov/documentation/services-web-api
    """

    def __init__(self, user_agent: str = "polytrader/0.1 (contact: you@example.com)"):
        self._client = httpx.AsyncClient(
            base_url=NWS_API,
            headers={
                "User-Agent": user_agent,
                "Accept": "application/geo+json",
            },
            timeout=20.0,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def points(self, p: NwsPoint) -> dict[str, Any]:
        r = await self._client.get(f"/points/{p.lat:.4f},{p.lon:.4f}")
        r.raise_for_status()
        return r.json()

    async def forecast_grid_data(self, grid_data_url: str) -> dict[str, Any]:
        # grid_data_url is usually absolute.
        r = await self._client.get(grid_data_url)
        r.raise_for_status()
        return r.json()


@dataclass(frozen=True)
class WeatherQuestion:
    """Parsed weather question from market text.

    This is intentionally basic. Real Polymarket markets often include a location + date.
    """

    kind: str  # currently only "rain"
    location: str | None
    target_date: datetime | None


_RAIN_PAT = re.compile(r"\brain\b|\bprecip(itation)?\b|\bshower(s)?\b", re.I)


def parse_weather_question(text: str) -> WeatherQuestion | None:
    if not _RAIN_PAT.search(text):
        return None

    # Very rough location extraction: "in <...>".
    m_loc = re.search(r"\bin\s+([A-Za-z0-9 .,'\-]{3,64})\??$", text.strip())
    location = m_loc.group(1).strip() if m_loc else None

    # Very rough date extraction: "on YYYY-MM-DD".
    m_date = re.search(r"\bon\s+(\d{4}-\d{2}-\d{2})\b", text)
    target_date = None
    if m_date:
        try:
            target_date = datetime.fromisoformat(m_date.group(1)).replace(tzinfo=timezone.utc)
        except ValueError:
            target_date = None

    return WeatherQuestion(kind="rain", location=location, target_date=target_date)


class LocationResolver:
    """Resolves a location string to a lat/lon.

    We avoid building in a hard dependency on external geocoding services.

    Provide a mapping via your own code, config file, or a small curated dictionary.
    """

    def __init__(self, mapping: dict[str, NwsPoint] | None = None):
        self.mapping = mapping or {}

    def resolve(self, location: str | None) -> NwsPoint | None:
        if not location:
            return None
        key = location.strip().lower()
        return self.mapping.get(key)


def _parse_iso(ts: str) -> datetime:
    # NWS returns RFC3339 timestamps.
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)


def _values_overlapping_window(values: list[dict[str, Any]], start: datetime, end: datetime) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for v in values:
        try:
            vs = _parse_iso(v["validTime"].split("/")[0])
        except Exception:
            continue
        # validTime often contains duration like "2026-.../PT1H"; we approximate the end.
        ve = vs + timedelta(hours=1)
        if ve <= start or vs >= end:
            continue
        out.append(v)
    return out


async def pop_signal_for_point(
    nws: NwsClient,
    point: NwsPoint,
    window_start: datetime,
    window_end: datetime,
) -> NwsPopSignal | None:
    meta = await nws.points(point)
    props = meta.get("properties") or {}
    grid_data_url = props.get("forecastGridData")
    if not grid_data_url:
        return None

    grid = await nws.forecast_grid_data(grid_data_url)
    gprops = grid.get("properties") or {}

    pop = gprops.get("probabilityOfPrecipitation") or {}
    values = pop.get("values") or []
    if not isinstance(values, list) or not values:
        return None

    overlapping = _values_overlapping_window(values, window_start, window_end)
    if not overlapping:
        return None

    # Use max PoP over the window as a conservative "will it rain" proxy.
    pops = [v.get("value") for v in overlapping]
    pops = [p for p in pops if isinstance(p, (int, float))]
    if not pops:
        return None

    p_rain = max(pops) / 100.0
    p_rain = max(0.0, min(1.0, p_rain))

    return NwsPopSignal(
        p_rain=p_rain,
        window_start=window_start,
        window_end=window_end,
        source="api.weather.gov forecastGridData probabilityOfPrecipitation",
        details=f"max PoP over window from {len(pops)} points",
    )
