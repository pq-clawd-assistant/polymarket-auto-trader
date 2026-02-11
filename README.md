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

## Dry run against real Polymarket markets (no trading)

This uses **Gamma + public CLOB** endpoints to fetch active markets and current token prices.
It does **not** place orders.

```bash
export POLYTRADER_EXCHANGE=polymarket-public
export POLYTRADER_MODE=paper
export POLYTRADER_MAX_MARKETS=200
polytrader once
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

Bitcoin price threshold markets (above/below by date):
- `polytrader/models/btc_threshold.py`: parses BTC above/below $K by YYYY-MM-DD markets and estimates probability using
  CoinGecko spot + realized volatility (GBM baseline)
- Settings: `POLYTRADER_BTC_VOL_LOOKBACK_DAYS`, `POLYTRADER_BTC_DRIFT_MU`

Sports + crypto (free sources added as signals):
- `polytrader/sources/espn.py` + `polytrader/models/sports_signals.py`: scoreboard snapshots (major leagues)
- `polytrader/sources/coingecko.py`, `defillama.py`, `feargreed.py` + `polytrader/models/crypto_signals.py`: basic crypto signals

These currently produce *signals*; turning them into per-market probabilities depends on how Polymarket words and resolves each market.

## Next steps (you tell me what API you end up using)

- Implement real `Exchange` adapter (market list, quotes/orderbook, place orders)
- Improve question parsing & market-specific resolution rules
- Add execution safeguards: max slippage, min volume, per-market cooldown, daily stop-loss, etc.

## Safety

Autotrading is risky. Prefer fractional Kelly, strict caps, and a kill switch.
