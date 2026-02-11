from __future__ import annotations

import asyncio
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from polytrader.sources.chainlink_streams import ChainlinkStreamsClient
from polytrader.sources.binance import realized_vol_from_closes

GAMMA = "https://gamma-api.polymarket.com"
SERIES_ID = 10192  # BTC up-or-down 15m
FEED_ID = "0x00039d9e45394f473ab1f050a1b963e6b05351e52d71e507509ada0c95ed75b8"


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class Trade:
    market_id: str
    slug: str
    title: str
    start: datetime
    end: datetime
    side: str  # Up|Down
    price: float
    stake_usd: float
    shares: float
    start_px: float | None = None
    end_px: float | None = None
    outcome: str | None = None
    pnl_usd: float | None = None


async def fetch_events(client: httpx.AsyncClient, limit: int = 25) -> list[dict]:
    r = await client.get(
        f"{GAMMA}/events",
        params={
            "series_id": str(SERIES_ID),
            "active": "true",
            "closed": "false",
            "order": "startTime",
            "ascending": "true",
            "limit": str(limit),
        },
        headers={"User-Agent": "polytrader-sim"},
        timeout=25.0,
    )
    r.raise_for_status()
    j = r.json()
    return j if isinstance(j, list) else []


def parse_active_markets(events: list[dict]) -> list[dict]:
    out = []
    for ev in events:
        if not isinstance(ev, dict):
            continue
        start_s = ev.get("startTime") or ev.get("eventStartTime")
        if not isinstance(start_s, str):
            continue
        try:
            start = datetime.fromisoformat(start_s.replace("Z", "+00:00")).astimezone(timezone.utc)
        except Exception:
            continue
        markets = ev.get("markets")
        if not (isinstance(markets, list) and markets):
            continue
        m = markets[0]
        if not isinstance(m, dict):
            continue
        end_s = m.get("endDate")
        if not isinstance(end_s, str):
            continue
        try:
            end = datetime.fromisoformat(end_s.replace("Z", "+00:00")).astimezone(timezone.utc)
        except Exception:
            continue
        out.append({"event": ev, "market": m, "start": start, "end": end})
    return out


def get_prices(market: dict) -> tuple[float, float] | None:
    # Gamma provides JSON string outcomePrices.
    op = market.get("outcomePrices")
    if not isinstance(op, str):
        return None
    try:
        arr = json.loads(op)
        if not (isinstance(arr, list) and len(arr) >= 2):
            return None
        up = float(arr[0])
        down = float(arr[1])
        return up, down
    except Exception:
        return None


async def chainlink_price_near(client: ChainlinkStreamsClient, *, target: datetime) -> float | None:
    # Use latest reports and pick the closest <= target.
    reports = await client.live_stream_reports(FEED_ID, limit=60)
    if not reports:
        return None
    target = target.astimezone(timezone.utc)
    # pick report with valid_from <= target, closest in time
    eligible = [r for r in reports if r.valid_from <= target]
    if not eligible:
        # if none <=, take earliest (closest after)
        eligible = reports
    best = min(eligible, key=lambda r: abs((r.valid_from - target).total_seconds()))
    return best.price


def _phi(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def prob_finish_up(*, spot: float, start_px: float, sigma_ann: float, remaining_seconds: float) -> float:
    """Approx P(S_end >= start_px) under GBM with drift 0, using lognormal from current spot."""
    if spot <= 0 or start_px <= 0 or sigma_ann <= 0 or remaining_seconds <= 0:
        return 0.5
    t_years = remaining_seconds / (365.0 * 24 * 3600)
    sigt = sigma_ann * math.sqrt(t_years)
    if sigt <= 0:
        return 0.5
    mu = -0.5 * sigma_ann**2 * t_years
    z = (math.log(start_px / spot) - mu) / sigt
    return max(0.0, min(1.0, 1.0 - _phi(z)))


async def simulate(
    duration_minutes: int,
    bankroll_btc: float,
    *,
    stake_frac: float = 0.06,
    edge_threshold: float = 0.02,
    settle_all: bool = True,
):
    log_path = Path("sim_logs")
    log_path.mkdir(exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_file = log_path / f"btc_updown_{run_id}.jsonl"

    gamma = httpx.AsyncClient()
    cl = ChainlinkStreamsClient()

    try:
        spot = await chainlink_price_near(cl, target=datetime.now(timezone.utc))
        if spot is None:
            raise RuntimeError("Could not fetch Chainlink spot")
        bankroll = bankroll_btc * spot

        trades: list[Trade] = []
        seen: set[str] = set()
        start = datetime.now(timezone.utc)
        end = start + timedelta(minutes=duration_minutes)

        async def log(obj: dict):
            out_file.write_text("", encoding="utf-8") if not out_file.exists() else None
            with out_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(obj, default=str) + "\n")

        await log({"type": "start", "ts": iso(start), "bankroll_btc": bankroll_btc, "spot": spot, "bankroll_usd": bankroll})

        while datetime.now(timezone.utc) < end:
            now = datetime.now(timezone.utc)

            events = await fetch_events(gamma, limit=20)
            markets = parse_active_markets(events)

            # Choose the current/next market whose interval contains now or starts soon.
            # We'll enter only once per market, near the start.
            for row in markets:
                m = row["market"]
                st: datetime = row["start"]
                en: datetime = row["end"]
                mid = str(m.get("id"))
                slug = str(m.get("slug"))
                title = str(m.get("question") or row["event"].get("title") or slug)

                if mid in seen:
                    continue

                # enter if within first 30s after start
                if not (st <= now <= st + timedelta(seconds=30)):
                    continue

                prices = get_prices(m)
                if not prices:
                    continue
                up_p, down_p = prices

                # Compute fair value p_up using Chainlink live spot + start_px and short-horizon vol.
                live_spot = await chainlink_price_near(cl, target=now)
                start_px = await chainlink_price_near(cl, target=st)

                # Estimate vol from Binance 1m closes (last ~4h)
                # 1m returns => periods/year ~ 60*24*365
                b = httpx.AsyncClient(base_url="https://api.binance.com", timeout=20.0)
                try:
                    resp = await b.get(
                        "/api/v3/klines",
                        params={"symbol": "BTCUSDT", "interval": "1m", "limit": "240"},
                        headers={"User-Agent": "polytrader-sim"},
                    )
                    resp.raise_for_status()
                    rows = resp.json()
                except Exception:
                    rows = []
                finally:
                    await b.aclose()

                closes = []
                try:
                    for row in rows:
                        closes.append(float(row[4]))
                except Exception:
                    closes = []

                sigma_ann = None
                if len(closes) >= 50:
                    sigma_ann = realized_vol_from_closes(closes, periods_per_year=60 * 24 * 365)
                sigma_ann = sigma_ann or 0.8

                remaining = max(1.0, (en - now).total_seconds())
                if live_spot is None or start_px is None:
                    p_up = 0.5
                else:
                    p_up = prob_finish_up(spot=live_spot, start_px=start_px, sigma_ann=sigma_ann, remaining_seconds=remaining)

                edge_up = p_up - up_p
                edge_down = (1 - p_up) - down_p

                if edge_up >= edge_down:
                    side = "Up"
                    price = up_p
                    edge = edge_up
                else:
                    side = "Down"
                    price = down_p
                    edge = edge_down

                if edge < edge_threshold:
                    await log({"type": "skip", "ts": iso(now), "market": mid, "slug": slug, "reason": "edge<threshold", "edge": edge})
                    seen.add(mid)
                    continue

                stake = bankroll * stake_frac
                if stake <= 0:
                    break
                shares = stake / max(1e-6, price)

                t = Trade(
                    market_id=mid,
                    slug=slug,
                    title=title,
                    start=st,
                    end=en,
                    side=side,
                    price=price,
                    stake_usd=stake,
                    shares=shares,
                    start_px=start_px,
                )
                trades.append(t)
                seen.add(mid)

                await log({
                    "type": "enter",
                    "ts": iso(now),
                    "market": mid,
                    "slug": slug,
                    "start": iso(st),
                    "end": iso(en),
                    "side": side,
                    "price": price,
                    "p_up": p_up,
                    "edge": edge,
                    "live_spot": live_spot,
                    "start_px": start_px,
                    "sigma_ann": sigma_ann,
                    "stake_usd": stake,
                    "bankroll_usd": bankroll,
                })

            # Settle any trades whose end passed.
            for t in trades:
                if t.pnl_usd is not None:
                    continue
                if now < t.end:
                    continue
                t.start_px = await chainlink_price_near(cl, target=t.start)
                t.end_px = await chainlink_price_near(cl, target=t.end)
                if t.start_px is None or t.end_px is None:
                    continue
                up = t.end_px >= t.start_px
                t.outcome = "Up" if up else "Down"
                win = t.outcome == t.side
                t.pnl_usd = (t.shares - t.stake_usd) if win else (-t.stake_usd)
                bankroll += t.pnl_usd
                await log({
                    "type": "settle",
                    "ts": iso(now),
                    "market": t.market_id,
                    "slug": t.slug,
                    "side": t.side,
                    "outcome": t.outcome,
                    "start_px": t.start_px,
                    "end_px": t.end_px,
                    "pnl_usd": t.pnl_usd,
                    "bankroll_usd": bankroll,
                })

            await asyncio.sleep(5)

        # If requested, keep running until all open trades settle.
        if settle_all and trades:
            last_end = max(t.end for t in trades)
            while datetime.now(timezone.utc) < last_end + timedelta(seconds=5):
                now = datetime.now(timezone.utc)
                for t in trades:
                    if t.pnl_usd is not None:
                        continue
                    if now < t.end:
                        continue
                    t.start_px = t.start_px or await chainlink_price_near(cl, target=t.start)
                    t.end_px = await chainlink_price_near(cl, target=t.end)
                    if t.start_px is None or t.end_px is None:
                        continue
                    up = t.end_px >= t.start_px
                    t.outcome = "Up" if up else "Down"
                    win = t.outcome == t.side
                    t.pnl_usd = (t.shares - t.stake_usd) if win else (-t.stake_usd)
                    bankroll += t.pnl_usd
                    await log({
                        "type": "settle",
                        "ts": iso(now),
                        "market": t.market_id,
                        "slug": t.slug,
                        "side": t.side,
                        "outcome": t.outcome,
                        "start_px": t.start_px,
                        "end_px": t.end_px,
                        "pnl_usd": t.pnl_usd,
                        "bankroll_usd": bankroll,
                    })
                await asyncio.sleep(5)

        end_ts = datetime.now(timezone.utc)
        await log({"type": "end", "ts": iso(end_ts), "bankroll_usd": bankroll, "trades": len(trades)})

        return out_file

    finally:
        await gamma.aclose()
        await cl.aclose()


if __name__ == "__main__":
    # 60 minutes, bankroll = 0.002 BTC
    p = asyncio.run(simulate(duration_minutes=60, bankroll_btc=0.002))
    print(str(p))
