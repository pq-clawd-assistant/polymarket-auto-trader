from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from polytrader.core.types import FairValue, Market
from polytrader.models.fair_value import FairValueModel
from polytrader.sources.binance import BinanceClient, parse_klines, realized_vol_from_closes
from polytrader.sources.chainlink_streams import ChainlinkStreamsClient, latest_price
from polytrader.storage.sqlite import Store


@dataclass(frozen=True)
class BtcUpDownInterval:
    start: datetime
    end: datetime


_UPDOWN_RE = re.compile(r"bitcoin\s+up\s+or\s+down", re.I)
_CHAINLINK_RE = re.compile(r"chain\.link/streams/btc-usd", re.I)


def is_btc_updown_15m_market(market: Market) -> bool:
    # Use question/title pattern and outcome labels.
    if market.outcomes != ("YES", "NO") and len(market.outcomes) == 2:
        # Gamma calls them Up/Down; we still accept if two outcomes.
        pass
    return bool(_UPDOWN_RE.search(market.question))


BTC_USD_CHAINLINK_FEED_ID = "0x00039d9e45394f473ab1f050a1b963e6b05351e52d71e507509ada0c95ed75b8"


class BtcUpDownIntervalFairValue(FairValueModel):
    """Fair value model for Polymarket's recurring "Bitcoin Up or Down" 15m markets.

    Resolution rule (per Gamma description):
      resolves to Up if price at end >= price at beginning, else Down.

    We approximate the settlement price stream with Binance BTCUSDT candles.
    The probability is P(S_end >= S_start).

    Under a symmetric/no-drift return model, this is ~0.5, so edge is typically small unless
    you add microstructure/momentum signals or exploit information lag.
    """

    def __init__(self, *, lookback_minutes: int = 240):
        self.lookback_minutes = lookback_minutes

    async def estimate(self, market: Market) -> FairValue:
        if not is_btc_updown_15m_market(market):
            return FairValue(market_id=market.id, p_yes=0.5, confidence=0.0, rationale="not BTC up/down")

        if not market.start_time or not market.close_time:
            return FairValue(market_id=market.id, p_yes=0.5, confidence=0.05, rationale="missing start/end")

        now = datetime.now(timezone.utc)
        if now >= market.close_time:
            return FairValue(market_id=market.id, p_yes=0.5, confidence=0.0, rationale="ended")

        store = Store()
        start_iso = market.start_time.astimezone(timezone.utc).isoformat()

        # Prefer Chainlink stream as the settlement source.
        cl = ChainlinkStreamsClient()
        try:
            live = await latest_price(cl, BTC_USD_CHAINLINK_FEED_ID)
        finally:
            await cl.aclose()

        spot = live.price if live else None

        # Start price: if we were running at the start, it should be recorded.
        start_px = store.get_start_price(market.id, start_iso)

        # Fallbacks:
        # - if start is very recent (<30m), approximate with Binance candle open at/after start
        if start_px is None:
            # Pull recent 1m candles.
            bc = BinanceClient()
            try:
                rows = await bc.klines(symbol="BTCUSDT", interval="1m", limit=1000)
                candles = parse_klines(rows)
            finally:
                await bc.aclose()

            if len(candles) >= 50:
                for c in candles:
                    if c.open_time >= market.start_time:
                        start_px = c.open
                        break
                start_px = start_px or candles[0].open

        if spot is None or start_px is None:
            return FairValue(market_id=market.id, p_yes=0.5, confidence=0.1, rationale="missing spot/start")

        # For vol, still use Binance 1m candles.
        bc = BinanceClient()
        try:
            rows = await bc.klines(symbol="BTCUSDT", interval="1m", limit=1000)
            candles = parse_klines(rows)
        finally:
            await bc.aclose()

        if len(candles) < 50:
            return FairValue(market_id=market.id, p_yes=0.5, confidence=0.1, rationale="insufficient candles")

        # Remaining time horizon
        remaining_seconds = max(1.0, (market.close_time - now).total_seconds())
        t_years = remaining_seconds / (365.0 * 24 * 3600)

        closes = [c.close for c in candles[-min(len(candles), self.lookback_minutes) :]]
        sigma_ann = realized_vol_from_closes(closes, periods_per_year=60 * 24 * 365) or 0.8

        # We want P(S_end >= start_px). Approx lognormal from current spot to end.
        # ln S_T ~ ln spot + (-0.5*sigma^2)T + sigma*sqrt(T) Z  (drift 0)
        if spot <= 0 or start_px <= 0:
            p_up = 0.5
        else:
            sigt = sigma_ann * math.sqrt(t_years)
            if sigt <= 0:
                p_up = 0.5
            else:
                mu = -0.5 * sigma_ann**2 * t_years
                z = (math.log(start_px / spot) - mu) / sigt
                # P(ln S_T >= ln start_px) = 1 - Phi(z)
                p_up = 0.5 * (1.0 - math.erf(z / math.sqrt(2.0)))
                p_up = max(0.0, min(1.0, p_up))

        # In Gamma, outcomes are ["Up","Down"]. Our system uses p_yes as probability of first outcome.
        # We treat YES ~= Up.
        p_yes = p_up

        rationale = (
            f"Chainlink live spot={spot:.2f}; start={start_px:.2f} (recorded if available; fallback=Binance); "
            f"rem={remaining_seconds/60:.1f}m; sigma~{sigma_ann:.2f}ann"
        )
        confidence = 0.30
        return FairValue(market_id=market.id, p_yes=p_yes, confidence=confidence, rationale=rationale)
