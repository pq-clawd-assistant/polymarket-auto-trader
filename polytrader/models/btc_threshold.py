from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from polytrader.core.types import FairValue, Market
from polytrader.models.fair_value import FairValueModel
from polytrader.sources.coingecko import CoinGeckoClient, price_signal_for_ids
from polytrader.sources.coingecko_marketchart import (
    CoinGeckoMarketChartClient,
    parse_market_chart,
    realized_vol_annualized,
)


@dataclass(frozen=True)
class BtcThresholdQuestion:
    direction: str  # "above"|"below"
    strike: float
    expiry: datetime


_DIR_RE = re.compile(r"\b(above|over|below|under)\b", re.I)
_BTC_RE = re.compile(r"\bbitcoin\b|\bbtc\b", re.I)
_USD_RE = re.compile(r"\$\s*([0-9]{1,3}(?:,[0-9]{3})*|[0-9]+)(?:\.(\d+))?\s*([kKmM])?")
_ISO_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


def _parse_strike(text: str) -> float | None:
    m = _USD_RE.search(text)
    if not m:
        return None
    whole = m.group(1).replace(",", "")
    frac = m.group(2)
    suf = (m.group(3) or "").lower()
    try:
        x = float(whole + ("." + frac if frac else ""))
    except Exception:
        return None
    mult = 1.0
    if suf == "k":
        mult = 1_000.0
    elif suf == "m":
        mult = 1_000_000.0
    return x * mult


def _parse_expiry(text: str) -> datetime | None:
    # MVP: require an ISO date (YYYY-MM-DD). We can extend later.
    m = _ISO_DATE_RE.search(text)
    if not m:
        return None
    try:
        d = datetime.fromisoformat(m.group(1)).replace(tzinfo=timezone.utc)
        # use end of day UTC
        return d.replace(hour=23, minute=59, second=59, microsecond=0)
    except Exception:
        return None


def parse_btc_threshold_question(text: str) -> BtcThresholdQuestion | None:
    if not _BTC_RE.search(text):
        return None

    mdir = _DIR_RE.search(text)
    if not mdir:
        return None
    w = mdir.group(1).lower()
    direction = "above" if w in ("above", "over") else "below"

    strike = _parse_strike(text)
    expiry = _parse_expiry(text)
    if strike is None or expiry is None:
        return None

    return BtcThresholdQuestion(direction=direction, strike=strike, expiry=expiry)


def _phi(x: float) -> float:
    # standard normal CDF
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def prob_above_lognormal(*, s0: float, k: float, sigma_ann: float, t_years: float, mu: float = 0.0) -> float:
    """P(S_T > K) under GBM with drift mu, vol sigma_ann.

    ln S_T ~ ln s0 + (mu - 0.5 sigma^2)T + sigma sqrt(T) Z
    """
    if s0 <= 0 or k <= 0 or sigma_ann <= 0 or t_years <= 0:
        return 0.5

    sigt = sigma_ann * math.sqrt(t_years)
    z = (math.log(k / s0) - (mu - 0.5 * sigma_ann**2) * t_years) / sigt
    p = 1.0 - _phi(z)
    return max(0.0, min(1.0, p))


class BtcAboveBelowFairValue(FairValueModel):
    """Fair value model for BTC above/below a USD strike by an ISO date.

    This is a simple quantitative model:
    - S0 from CoinGecko spot price
    - sigma from realized vol of CoinGecko hourly prices over lookback window
    - GBM with configurable drift (default 0)

    IMPORTANT: This is a crude baseline, not a calibrated options model.
    """

    def __init__(self, *, vol_lookback_days: int = 30, drift_mu: float = 0.0):
        self.vol_lookback_days = vol_lookback_days
        self.drift_mu = drift_mu

    async def estimate(self, market: Market) -> FairValue:
        q = parse_btc_threshold_question(market.question)
        if not q:
            return FairValue(market_id=market.id, p_yes=0.5, confidence=0.0, rationale="not BTC threshold")

        now = datetime.now(timezone.utc)
        if q.expiry <= now:
            return FairValue(market_id=market.id, p_yes=0.5, confidence=0.0, rationale="expired")

        # spot
        cg = CoinGeckoClient()
        try:
            spot = await price_signal_for_ids(cg, ["bitcoin"])
        finally:
            await cg.aclose()

        if not spot:
            return FairValue(market_id=market.id, p_yes=0.5, confidence=0.05, rationale="spot unavailable")

        s0 = spot[0].price_usd

        # vol
        mc = CoinGeckoMarketChartClient()
        try:
            j = await mc.market_chart("bitcoin", vs_currency="usd", days=self.vol_lookback_days)
            chart = parse_market_chart("bitcoin", "usd", self.vol_lookback_days, j)
        finally:
            await mc.aclose()

        px = [p for _, p in chart.prices]
        # hourly series => ~24*365 periods/year
        sigma = realized_vol_annualized(px, periods_per_year=24 * 365)
        if sigma is None or sigma <= 0:
            sigma = 0.8  # fallback (very rough)
            conf = 0.2
            vol_note = "fallback sigma"
        else:
            conf = 0.45
            vol_note = f"realized vol {sigma:.2f} ann"

        t_years = (q.expiry - now).total_seconds() / (365.0 * 24 * 3600)
        p_above = prob_above_lognormal(s0=s0, k=q.strike, sigma_ann=sigma, t_years=t_years, mu=self.drift_mu)

        if q.direction == "above":
            p_yes = p_above
        else:
            p_yes = 1.0 - p_above

        rationale = f"CoinGecko spot={s0:.0f}, strike={q.strike:.0f}, T={t_years:.3f}y, {vol_note}"
        # Confidence is intentionally moderate.
        confidence = conf

        return FairValue(market_id=market.id, p_yes=p_yes, confidence=confidence, rationale=rationale)
