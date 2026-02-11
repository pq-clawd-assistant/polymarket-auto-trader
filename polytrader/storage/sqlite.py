from __future__ import annotations

import sqlite3
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from polytrader.core.types import Fill, Opportunity


class Store:
    def __init__(self, path: str = "polytrader.db"):
        self.path = Path(path)
        self._init()

    def _init(self) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """
                create table if not exists fills (
                  ts text,
                  market_id text,
                  side text,
                  fraction real,
                  avg_price real
                );
                """
            )
            conn.execute(
                """
                create table if not exists opportunities (
                  ts text,
                  market_id text,
                  question text,
                  side text,
                  edge real,
                  suggested_fraction real,
                  implied_yes real,
                  fv_yes real,
                  confidence real
                );
                """
            )

    def log_opportunity(self, opp: Opportunity) -> None:
        ts = datetime.utcnow().isoformat()
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """
                insert into opportunities values (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    ts,
                    opp.market.id,
                    opp.market.question,
                    opp.side,
                    float(opp.edge),
                    float(opp.suggested_fraction),
                    float(opp.quote.yes_price),
                    float(opp.fv.p_yes),
                    float(opp.fv.confidence),
                    float(opp.fv.confidence),
                ),
            )

    def log_fill(self, fill: Fill) -> None:
        ts = fill.ts.isoformat()
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "insert into fills values (?,?,?,?,?)",
                (ts, fill.order.market_id, fill.order.side, fill.filled_fraction, fill.avg_price),
            )
