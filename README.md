# Polymarket Auto Trader (framework)

Repo: paper-trading + strategy framework for a Polymarket-style autonomous trader.

This is **not** a profit machine. It’s a scaffold you can run elsewhere and wire to the actual exchange API once you have it.

## What’s implemented (MVP)

- Market/quote/fair-value types
- Opportunity detection using an **edge threshold**
- Fractional Kelly sizing + hard caps
- A stub `PaperExchange`
- SQLite logging (`polytrader.db`)
- CLI runner

## Requirements

- Python 3.11+

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
```

## Run (paper)

```bash
polytrader once
polytrader run
```

Configuration via env vars (prefix `POLYTRADER_`), e.g.

```bash
export POLYTRADER_INTERVAL_SECONDS=600
export POLYTRADER_MIN_EDGE=0.08
export POLYTRADER_MODE=paper
```

## Edge sources (started)

Weather (NWS/NOAA):
- `polytrader/sources/nws.py`: minimal `api.weather.gov` client
- `polytrader/models/weather.py`: PoP-based proxy fair value for simple rain/precip questions
- `POLYTRADER_LOCATIONS_FILE`: optional JSON mapping from location string → lat/lon
  (see `polytrader/config/locations.example.json`)

Sports + crypto are placeholders in the roadmap; we’ll add them once we pick concrete data sources.

## Next steps (you tell me what API you end up using)

- Implement real `Exchange` adapter (market list, quotes/orderbook, place orders)
- Improve question parsing & market-specific resolution rules
- Add execution safeguards: max slippage, min volume, per-market cooldown, daily stop-loss, etc.

## Safety

Autotrading is risky. Prefer fractional Kelly, strict caps, and a kill switch.
