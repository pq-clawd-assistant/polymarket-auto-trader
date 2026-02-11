from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx


ESPN = "https://site.api.espn.com/apis/site/v2/sports"


@dataclass(frozen=True)
class EspnScoreboardEvent:
    league: str
    name: str
    start_time: datetime | None
    status: str | None
    home: str | None
    away: str | None
    home_score: int | None
    away_score: int | None
    ts: datetime
    source: str = "espn"


class EspnClient:
    """Unofficial-ish ESPN site API client.

    This is widely used but not guaranteed stable.
    """

    def __init__(self):
        self._client = httpx.AsyncClient(timeout=20.0)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def scoreboard(self, sport: str, league: str, *, date: str | None = None) -> dict[str, Any]:
        # Examples:
        # sport=nfl, league=nfl
        # sport=basketball, league=nba
        url = f"{ESPN}/{sport}/{league}/scoreboard"
        params = {"dates": date} if date else None
        r = await self._client.get(url, params=params)
        r.raise_for_status()
        return r.json()


def _parse_iso(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def parse_scoreboard(league_key: str, j: dict[str, Any]) -> list[EspnScoreboardEvent]:
    ts = datetime.now(timezone.utc)
    out: list[EspnScoreboardEvent] = []
    events = j.get("events")
    if not isinstance(events, list):
        return out
    for e in events:
        try:
            name = str(e.get("name") or e.get("shortName") or "")
            start = _parse_iso(str(e.get("date"))) if e.get("date") else None
            status = None
            st = e.get("status", {}).get("type", {}) if isinstance(e.get("status"), dict) else {}
            if isinstance(st, dict):
                status = st.get("description") or st.get("name")
            comps = e.get("competitions")
            home = away = None
            hs = aws = None
            if isinstance(comps, list) and comps:
                competitors = comps[0].get("competitors")
                if isinstance(competitors, list):
                    for c in competitors:
                        if not isinstance(c, dict):
                            continue
                        side = c.get("homeAway")
                        team = c.get("team", {})
                        tname = team.get("displayName") if isinstance(team, dict) else None
                        score = c.get("score")
                        try:
                            score_i = int(score) if score is not None else None
                        except Exception:
                            score_i = None
                        if side == "home":
                            home, hs = tname, score_i
                        elif side == "away":
                            away, aws = tname, score_i
            out.append(
                EspnScoreboardEvent(
                    league=league_key,
                    name=name,
                    start_time=start,
                    status=str(status) if status is not None else None,
                    home=str(home) if home is not None else None,
                    away=str(away) if away is not None else None,
                    home_score=hs,
                    away_score=aws,
                    ts=ts,
                )
            )
        except Exception:
            continue
    return out
