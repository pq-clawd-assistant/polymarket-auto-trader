from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from polytrader.core.types import FairValue, Market
from polytrader.models.fair_value import FairValueModel
from polytrader.sources.binance import BinanceClient, parse_klines, realized_vol_from_closes


@dataclass(frozen=True)
class Btc15mQuestion:
    direction: str  # "up"|"down"
    horizon_minutes: int


_BTC_RE = re.compile(r"\bbitcoin\b|\bbtc\b", re.I)
_UP_RE = re.compile(r"\b(up|higher|increase|rise)\b", re.I)
_DOWN_RE = re.compile(r"\b(down|lower|decrease|fall)\b", re.I)
_15M_RE = re.compile(r"\b15\s*(min|mins|minute|minutes)\b", re.I)


def parse_btc_15m_direction(text: str) -> Btc15mQuestion | None:
    if not _BTC_RE.search(text):
        return None
    if not _15M_RE.search(text):
        return None
    up = bool(_UP_RE.search(text))
    down = bool(_DOWN_RE.search(text))
    if up == down:
        return None
    return Btc15mQuestion(direction="up" if up else "down", horizon_minutes=15)


def _phi(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


class Btc15mUpDownFairValue(FairValueModel):
    """Fair value for "BTC up/down in 15 minutes" style markets.

    Model:
    - Pull recent 1m candles for BTCUSDT from Binance.
    - Estimate short-horizon volatility from recent 1m log returns.
    - Assume drift ~ 0 and symmetric distribution for 15m return.

    Under this baseline, P(up) ~= 0.5; edge can only come from:
    - microstructure signals (not implemented)
    - information lag between market phrasing and external price feed

    This is still useful for wiring the pipeline and for later enhancements.
    """

    def __init__(self, *, lookback_minutes: int = 240):
        self.lookback_minutes = lookback_minutes

    async def estimate(self, market: Market) -> FairValue:
        q = parse_btc_15m_direction(market.question)
        if not q:
            return FairValue(market_id=market.id, p_yes=0.5, confidence=0.0, rationale="not BTC 15m up/down")

        bc = BinanceClient()
        try:
            rows = await bc.klines(symbol="BTCUSDT", interval="1m", limit=min(1000, self.lookback_minutes))
            candles = parse_klines(rows)
        finally:
            await bc.aclose()

        if len(candles) < 50:
            return FairValue(market_id=market.id, p_yes=0.5, confidence=0.1, rationale="insufficient candles")

        closes = [c.close for c in candles]
        s0 = closes[-1]

        # 1m returns => periods/year approx 60*24*365
        sigma_ann = realized_vol_from_closes(closes, periods_per_year=60 * 24 * 365) or 0.8

        # For sign of return under 0 drift and symmetric noise: P(up)=0.5.
        # But we include a tiny correction for discrete tick/rounding by modeling P(ST>S0).
        t_years = (q.horizon_minutes * 60.0) / (365.0 * 24 * 3600)
        sigt = sigma_ann * math.sqrt(t_years)
        if sigt <= 0:
            p_up = 0.5
        else:
            # With GBM drift 0, median is S0*exp(-0.5*sigma^2 T). So P(ST>S0) < 0.5 slightly.
            # Approx using normal: ln(ST/S0) ~ N(-0.5*sigma^2 T, sigma*sqrt(T))
            mu = -0.5 * sigma_ann**2 * t_years
            z = (0 - mu) / sigt
            p_up = 1.0 - _phi(z)
            p_up = max(0.0, min(1.0, p_up))

        p_yes = p_up if q.direction == "up" else (1.0 - p_up)

        rationale = f"Binance BTCUSDT 1m; s0={s0:.0f}; sigma~{sigma_ann:.2f}ann; horizon=15m"
        confidence = 0.25
        return FairValue(market_id=market.id, p_yes=p_yes, confidence=confidence, rationale=rationale)
