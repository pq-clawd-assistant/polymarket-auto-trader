from __future__ import annotations

import json
from pathlib import Path

from polytrader.core.types import FairValue, Market
from polytrader.models.fair_value import FairValueModel, HeuristicBaseline
from polytrader.models.btc_15m import Btc15mUpDownFairValue, parse_btc_15m_direction
from polytrader.models.btc_threshold import BtcAboveBelowFairValue, parse_btc_threshold_question
from polytrader.models.btc_updown_interval import BtcUpDownIntervalFairValue, is_btc_updown_15m_market
from polytrader.models.weather import NwsRainFairValue
from polytrader.sources.nws import LocationResolver, NwsPoint, parse_weather_question
from polytrader.settings import settings


def _load_locations(path: str | None) -> dict[str, NwsPoint]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    data = json.loads(p.read_text())
    out: dict[str, NwsPoint] = {}
    for k, v in data.items():
        try:
            out[str(k).strip().lower()] = NwsPoint(lat=float(v["lat"]), lon=float(v["lon"]))
        except Exception:
            continue
    return out


class RouterFairValueModel(FairValueModel):
    """Routes markets to the first matching fair value model.

    Current routing:
    - if market question looks like a rain/precip market -> NWS PoP-based model
    - else -> baseline

    Extend this with additional category-specific models.
    """

    def __init__(self):
        mapping = _load_locations(settings.locations_file)
        self._resolver = LocationResolver(mapping)
        self._weather = NwsRainFairValue(user_agent=settings.nws_user_agent, resolver=self._resolver)
        self._btc = BtcAboveBelowFairValue(
            vol_lookback_days=settings.btc_vol_lookback_days,
            drift_mu=settings.btc_drift_mu,
        )
        self._btc15m = Btc15mUpDownFairValue(lookback_minutes=settings.btc_15m_lookback_minutes)
        self._btc_updown = BtcUpDownIntervalFairValue(lookback_minutes=settings.btc_15m_lookback_minutes)
        self._baseline = HeuristicBaseline()

    async def estimate(self, market: Market) -> FairValue:
        if is_btc_updown_15m_market(market):
            return await self._btc_updown.estimate(market)
        if parse_btc_15m_direction(market.question):
            return await self._btc15m.estimate(market)
        if parse_btc_threshold_question(market.question):
            return await self._btc.estimate(market)
        if parse_weather_question(market.question):
            return await self._weather.estimate(market)
        return await self._baseline.estimate(market)

    async def aclose(self) -> None:
        await self._weather.aclose()
