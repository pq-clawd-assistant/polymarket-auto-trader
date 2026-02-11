from __future__ import annotations

from datetime import datetime, timedelta, timezone

from polytrader.core.types import FairValue, Market
from polytrader.models.fair_value import FairValueModel
from polytrader.sources.nws import LocationResolver, NwsClient, parse_weather_question, pop_signal_for_point


class NwsRainFairValue(FairValueModel):
    """Fair value estimator for simple "Will it rain ..." markets.

    This model:
    - parses the market question looking for rain/precip keywords
    - resolves the location string to a lat/lon (you provide mapping)
    - queries NWS grid forecast data and converts PoP to a probability

    Notes:
    - This is a *proxy*. Many markets have more specific definitions than "PoP > 0".
    - The mapping from forecast PoP to an event probability is non-trivial.
      Using max(PoP) is a conservative heuristic.
    """

    def __init__(
        self,
        *,
        user_agent: str,
        resolver: LocationResolver,
        default_window_hours: int = 24,
    ):
        self._nws = NwsClient(user_agent=user_agent)
        self._resolver = resolver
        self._default_window_hours = default_window_hours

    async def estimate(self, market: Market) -> FairValue:
        q = parse_weather_question(market.question)
        if not q:
            return FairValue(market_id=market.id, p_yes=0.5, confidence=0.0, rationale="not weather")

        point = self._resolver.resolve(q.location)
        if not point:
            return FairValue(
                market_id=market.id,
                p_yes=0.5,
                confidence=0.05,
                rationale=f"weather market but location unresolved: {q.location!r}",
            )

        now = datetime.now(timezone.utc)
        if q.target_date:
            # Use the target date as a day window in UTC (simple).
            window_start = q.target_date.replace(hour=0, minute=0, second=0, microsecond=0)
            window_end = window_start + timedelta(days=1)
        else:
            window_start = now
            window_end = now + timedelta(hours=self._default_window_hours)

        sig = await pop_signal_for_point(self._nws, point, window_start, window_end)
        if not sig:
            return FairValue(market_id=market.id, p_yes=0.5, confidence=0.05, rationale="NWS signal unavailable")

        # Convert PoP proxy to FV.
        # (For now: p_yes := p_rain)
        p_yes = sig.p_rain

        confidence = 0.55  # heuristic; can be improved with lead time, ensemble spread, etc.
        rationale = f"NWS PoP proxy ({sig.details})"

        return FairValue(market_id=market.id, p_yes=p_yes, confidence=confidence, rationale=rationale)

    async def aclose(self) -> None:
        await self._nws.aclose()
