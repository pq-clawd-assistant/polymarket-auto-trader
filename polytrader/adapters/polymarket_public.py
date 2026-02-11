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
    gamma_yes_price: float | None = None
    gamma_no_price: float | None = None


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

    Notes:
    - Many Polymarket markets are restricted; public CLOB price endpoints may fail.
      We therefore fall back to Gamma "outcomePrices" as needed.
    """

    def __init__(self, *, user_agent: str = "polytrader/0.1"):
        self._gamma = httpx.AsyncClient(base_url=GAMMA, timeout=25.0, headers={"User-Agent": user_agent})
        self._clob = httpx.AsyncClient(base_url=CLOB, timeout=25.0, headers={"User-Agent": user_agent})
        self._meta: dict[str, PolyMarketMeta] = {}

    async def aclose(self) -> None:
        await self._gamma.aclose()
        await self._clob.aclose()

    def _ingest_market_row(self, out: list[Market], m: dict[str, Any], *, category: str | None) -> None:
        mid = m.get("id")
        question = m.get("question")
        if not (isinstance(mid, str) and isinstance(question, str)):
            return

        clob_ids = m.get("clobTokenIds")
        yes_id = no_id = None
        if isinstance(clob_ids, str):
            clob_ids = _parse_json_array(clob_ids)
        if isinstance(clob_ids, list) and len(clob_ids) >= 2:
            if isinstance(clob_ids[0], str) and isinstance(clob_ids[1], str):
                yes_id, no_id = clob_ids[0], clob_ids[1]

        # Parse outcomes/outcomePrices (Gamma provides these as JSON strings)
        outcomes = m.get("outcomes")
        outcome_prices = m.get("outcomePrices")
        outcomes_arr = _parse_json_array(outcomes) if isinstance(outcomes, str) else []
        prices_arr = _parse_json_array(outcome_prices) if isinstance(outcome_prices, str) else []

        gamma_yes = gamma_no = None
        try:
            if len(prices_arr) >= 2:
                gamma_yes = float(prices_arr[0])
                gamma_no = float(prices_arr[1])
        except Exception:
            gamma_yes = gamma_no = None

        # If token ids are missing, we can still quote from outcomePrices by returning synthetic ids.
        if not (yes_id and no_id):
            yes_id = f"gamma:{mid}:YES"
            no_id = f"gamma:{mid}:NO"

        liquidity = None
        for k in ("liquidity", "liquidityNum", "liquidityUSD", "liquidityClob"):
            v = m.get(k)
            if isinstance(v, (int, float)):
                liquidity = float(v)
                break
            if isinstance(v, str):
                try:
                    liquidity = float(v)
                    break
                except Exception:
                    pass

        self._meta[mid] = PolyMarketMeta(
            yes_token_id=yes_id,
            no_token_id=no_id,
            liquidity=liquidity,
            gamma_yes_price=gamma_yes,
            gamma_no_price=gamma_no,
        )

        # start/end times
        start_time = None
        end_time = None
        for k in ("eventStartTime", "startTime"):
            if isinstance(m.get(k), str):
                try:
                    start_time = datetime.fromisoformat(m[k].replace("Z", "+00:00")).astimezone(timezone.utc)
                    break
                except Exception:
                    start_time = None
        if isinstance(m.get("endDate"), str):
            try:
                end_time = datetime.fromisoformat(m["endDate"].replace("Z", "+00:00")).astimezone(timezone.utc)
            except Exception:
                end_time = None

        outs = None
        if len(outcomes_arr) >= 2:
            outs = (str(outcomes_arr[0]), str(outcomes_arr[1]))

        out.append(
            Market(
                id=mid,
                question=question,
                category=str(category) if category is not None else None,
                start_time=start_time,
                close_time=end_time,
                outcomes=outs or ("YES", "NO"),
            )
        )

    async def list_markets(self, limit: int) -> list[Market]:
        """List markets.

        Strategy:
        - If POLYTRADER_GAMMA_SERIES_ID is provided, use /events?series_id=... (best for recurring series).
        - Else, use /markets (broad discovery).
        """

        from polytrader.settings import settings

        out: list[Market] = []
        self._meta.clear()

        if settings.gamma_series_id is not None:
            r = await self._gamma.get(
                "/events",
                params={
                    "series_id": str(settings.gamma_series_id),
                    "active": "true",
                    "closed": "false",
                    "limit": str(limit),
                    "order": "startTime",
                    "ascending": "true",
                },
            )
            r.raise_for_status()
            events = r.json()
            if not isinstance(events, list):
                return []

            for ev in events:
                if not isinstance(ev, dict):
                    continue
                category = None
                tags = ev.get("tags")
                if isinstance(tags, list) and tags and isinstance(tags[0], dict):
                    category = tags[0].get("label") or tags[0].get("slug")

                markets = ev.get("markets")
                if not isinstance(markets, list):
                    continue

                for m in markets:
                    if not isinstance(m, dict):
                        continue
                    # inject event startTime if present
                    if isinstance(ev.get("startTime"), str):
                        m = dict(m)
                        m.setdefault("eventStartTime", ev["startTime"])
                    self._ingest_market_row(out, m, category=category)

            return out[:limit]

        # Fallback: broad /markets endpoint
        r = await self._gamma.get(
            "/markets",
            params={
                "active": "true",
                "closed": "false",
                "limit": str(limit),
            },
        )
        r.raise_for_status()
        rows = r.json()
        if not isinstance(rows, list):
            return []

        for m in rows:
            if not isinstance(m, dict):
                continue
            category = None
            events = m.get("events")
            if isinstance(events, list) and events and isinstance(events[0], dict):
                tags = events[0].get("tags")
                if isinstance(tags, list) and tags and isinstance(tags[0], dict):
                    category = tags[0].get("label") or tags[0].get("slug")
            self._ingest_market_row(out, m, category=category)

        return out[:limit]

    async def _clob_price(self, token_id: str) -> float | None:
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

            yes: float | None = None
            no: float | None = None

            # Try CLOB first if token ids look real.
            if not meta.yes_token_id.startswith("gamma:"):
                yes = await self._clob_price(meta.yes_token_id)
                no = await self._clob_price(meta.no_token_id)

            # Fallback to Gamma outcomePrices when CLOB is unavailable/restricted.
            if yes is None or no is None:
                if meta.gamma_yes_price is not None and meta.gamma_no_price is not None:
                    yes, no = meta.gamma_yes_price, meta.gamma_no_price

            if yes is None or no is None:
                continue

            yes = max(0.0, min(1.0, float(yes)))
            no = max(0.0, min(1.0, float(no)))

            # If CLOB returned nonsense zeros but Gamma has values, prefer Gamma.
            if (yes < 0.01 or no < 0.01) and meta.gamma_yes_price is not None and meta.gamma_no_price is not None:
                yes = max(0.0, min(1.0, float(meta.gamma_yes_price)))
                no = max(0.0, min(1.0, float(meta.gamma_no_price)))

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
