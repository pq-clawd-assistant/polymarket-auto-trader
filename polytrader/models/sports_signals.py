from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from polytrader.sources.espn import EspnClient, EspnScoreboardEvent, parse_scoreboard


@dataclass(frozen=True)
class SportsSignals:
    ts: datetime
    events: list[EspnScoreboardEvent]


# A pragmatic set of major leagues.
# ESPN uses sport/league pairs.
LEAGUES: list[tuple[str, str, str]] = [
    ("football", "nfl", "NFL"),
    ("basketball", "nba", "NBA"),
    ("basketball", "wnba", "WNBA"),
    ("baseball", "mlb", "MLB"),
    ("hockey", "nhl", "NHL"),
    ("soccer", "eng.1", "EPL"),
    ("soccer", "uefa.champions", "UCL"),
    ("soccer", "usa.1", "MLS"),
]


async def fetch_sports_scoreboards(*, date: str | None = None) -> SportsSignals:
    """Fetch free-ish sports schedule/scoreboard snapshots via ESPN site API.

    This is a starting point. Injury/status signals are trickier to do reliably for free.
    """

    ts = datetime.now(timezone.utc)
    client = EspnClient()
    try:
        events: list[EspnScoreboardEvent] = []
        for sport, league, label in LEAGUES:
            j = await client.scoreboard(sport, league, date=date)
            events.extend(parse_scoreboard(label, j))
        return SportsSignals(ts=ts, events=events)
    finally:
        await client.aclose()
