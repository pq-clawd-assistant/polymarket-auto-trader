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

    def get_start_price(self, market_id: str, start_time_iso: str) -> float | None:
        with sqlite3.connect(self.path) as conn:
            cur = conn.execute(
                "select price from start_prices where market_id=? and start_time=?",
                (market_id, start_time_iso),
            )
            row = cur.fetchone()
            return float(row[0]) if row else None

    def set_start_price(self, market_id: str, start_time_iso: str, price: float, source: str) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "insert or replace into start_prices values (?,?,?,?)",
                (market_id, start_time_iso, float(price), source),
            )

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
            conn.execute(
                """
                create table if not exists start_prices (
                  market_id text,
                  start_time text,
                  price real,
                  source text,
                  primary key (market_id, start_time)
                );
                """
            )

    def log_opportunity(self, opp: Opportunity) -> None:
        ts = datetime.utcnow().isoformat()
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """
                insert into opportunities values (?,?,?,?,?,?,?,?,?)
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
                ),
            )

    def log_fill(self, fill: Fill) -> None:
        ts = fill.ts.isoformat()
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "insert into fills values (?,?,?,?,?)",
                (ts, fill.order.market_id, fill.order.side, fill.filled_fraction, fill.avg_price),
            )
