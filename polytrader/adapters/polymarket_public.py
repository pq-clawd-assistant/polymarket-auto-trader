from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from polytrader.adapters.exchange import Exchange
from polytrader.core.types import Fill, Market, MarketQuote, Order


GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"


@dataclass(frozen=True)
class PolyMarketMeta:
    yes_token_id: str
    no_token_id: str
    liquidity: float | None = None


def _parse_json_array(s: str) -> list[Any]:
    try:
        v = json.loads(s)
        return v if isinstance(v, list) else []
    except Exception:
        return []


class PolymarketPublicExchange(Exchange):
    """Read-only Polymarket adapter using Gamma + public CLOB endpoints.

    This supports DRY RUN / PAPER decisions without authenticated order placement.

    Sources:
    - Gamma events/markets: https://gamma-api.polymarket.com
    - CLOB price/book (public): https://clob.polymarket.com

    Docs: https://docs.polymarket.com/quickstart/fetching-data

    Limitations:
    - We fetch a "buy" price for YES/NO outcome tokens and treat it as the implied probability.
    - We do not simulate fills from the orderbook; this is a coarse approximation.
    """

    def __init__(self, *, user_agent: str = "polytrader/0.1"):
        self._gamma = httpx.AsyncClient(base_url=GAMMA, timeout=25.0, headers={"User-Agent": user_agent})
        self._clob = httpx.AsyncClient(base_url=CLOB, timeout=25.0, headers={"User-Agent": user_agent})
        self._meta: dict[str, PolyMarketMeta] = {}

    async def aclose(self) -> None:
        await self._gamma.aclose()
        await self._clob.aclose()

    async def list_markets(self, limit: int) -> list[Market]:
        # Pull events including embedded markets.
        r = await self._gamma.get(
            "/events",
            params={
                "active": "true",
                "closed": "false",
                "limit": str(limit),
            },
        )
        r.raise_for_status()
        events = r.json()
        if not isinstance(events, list):
            return []

        out: list[Market] = []
        self._meta.clear()

        for ev in events:
            if not isinstance(ev, dict):
                continue
            tags = ev.get("tags")
            category = None
            if isinstance(tags, list) and tags:
                t0 = tags[0]
                if isinstance(t0, dict):
                    category = t0.get("label") or t0.get("slug")

            markets = ev.get("markets")
            if not isinstance(markets, list):
                continue
            for m in markets:
                if not isinstance(m, dict):
                    continue
                mid = m.get("id")
                question = m.get("question")
                if not (isinstance(mid, str) and isinstance(question, str)):
                    continue

                clob_ids = m.get("clobTokenIds")
                # docs show clobTokenIds as list[str]
                yes_id = no_id = None
                if isinstance(clob_ids, list) and len(clob_ids) >= 2:
                    if isinstance(clob_ids[0], str) and isinstance(clob_ids[1], str):
                        yes_id, no_id = clob_ids[0], clob_ids[1]

                # fallback: parse outcomes/outcomePrices if present
                outcomes = m.get("outcomes")
                outcome_prices = m.get("outcomePrices")
                outcomes_arr = _parse_json_array(outcomes) if isinstance(outcomes, str) else []
                prices_arr = _parse_json_array(outcome_prices) if isinstance(outcome_prices, str) else []

                # If token ids are missing, we can still quote from outcomePrices by returning synthetic ids.
                if not (yes_id and no_id):
                    yes_id = f"gamma:{mid}:YES"
                    no_id = f"gamma:{mid}:NO"

                liquidity = None
                for k in ("liquidity", "liquidityNum", "liquidityUSD"):
                    v = m.get(k)
                    if isinstance(v, (int, float)):
                        liquidity = float(v)
                        break

                self._meta[mid] = PolyMarketMeta(yes_token_id=yes_id, no_token_id=no_id, liquidity=liquidity)

                out.append(
                    Market(
                        id=mid,
                        question=question,
                        category=str(category) if category is not None else None,
                        close_time=None,
                        outcomes=("YES", "NO"),
                    )
                )

        return out[:limit]

    async def _clob_price(self, token_id: str) -> float | None:
        # CLOB /price expects token_id and side=buy|sell
        r = await self._clob.get("/price", params={"token_id": token_id, "side": "buy"})
        if r.status_code != 200:
            return None
        j = r.json()
        p = j.get("price") if isinstance(j, dict) else None
        try:
            return float(p)
        except Exception:
            return None

    async def get_quotes(self, market_ids: list[str]) -> list[MarketQuote]:
        out: list[MarketQuote] = []
        ts = datetime.now(timezone.utc)

        for mid in market_ids:
            meta = self._meta.get(mid)
            if not meta:
                continue

            # If token ids are synthetic gamma:* then we can't query CLOB.
            if meta.yes_token_id.startswith("gamma:"):
                # no quote; skip
                continue

            yes = await self._clob_price(meta.yes_token_id)
            no = await self._clob_price(meta.no_token_id)
            if yes is None or no is None:
                continue

            # Theoretically yes+no ~= 1; keep as-is but clamp.
            yes = max(0.0, min(1.0, yes))
            no = max(0.0, min(1.0, no))

            out.append(
                MarketQuote(
                    market_id=mid,
                    yes_price=yes,
                    no_price=no,
                    liquidity_usd=meta.liquidity,
                    ts=ts,
                )
            )

        return out

    async def place_order(self, order: Order) -> Fill:
        raise RuntimeError("PolymarketPublicExchange is read-only; use a live adapter for order placement.")
