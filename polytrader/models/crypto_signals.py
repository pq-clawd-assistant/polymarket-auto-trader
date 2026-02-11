from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from polytrader.sources.coingecko import CoinGeckoClient, CgPriceSignal, price_signal_for_ids
from polytrader.sources.defillama import DefiLlamaClient, LlamaTvlSignal, top_chain_tvl
from polytrader.sources.feargreed import FearGreedClient, FearGreedSignal, latest_fear_greed


@dataclass(frozen=True)
class CryptoSignals:
    ts: datetime
    prices: list[CgPriceSignal]
    chains_tvl: list[LlamaTvlSignal]
    fear_greed: FearGreedSignal | None


# Common coin-id mapping for CoinGecko
_COIN_IDS = {
    "btc": "bitcoin",
    "bitcoin": "bitcoin",
    "eth": "ethereum",
    "ethereum": "ethereum",
    "sol": "solana",
    "solana": "solana",
}


def extract_coin_ids(text: str) -> list[str]:
    t = text.lower()
    ids: set[str] = set()
    for k, v in _COIN_IDS.items():
        if re.search(rf"\b{re.escape(k)}\b", t):
            ids.add(v)
    return sorted(ids)


async def fetch_crypto_signals(*, text: str) -> CryptoSignals:
    """Fetch a small set of free crypto signals.

    - CoinGecko: spot price + 24h change/vol/mcap for coin ids mentioned in text
    - DefiLlama: top chain TVL snapshot
    - Alternative.me: Fear & Greed index

    This returns *signals* only; mapping these to market probabilities depends on the market question.
    """

    ts = datetime.now(timezone.utc)

    cg = CoinGeckoClient()
    llama = DefiLlamaClient()
    fg = FearGreedClient()

    try:
        ids = extract_coin_ids(text)
        prices = await price_signal_for_ids(cg, ids) if ids else []
        chains = await top_chain_tvl(llama, limit=25)
        fgs = await latest_fear_greed(fg)
        return CryptoSignals(ts=ts, prices=prices, chains_tvl=chains, fear_greed=fgs)
    finally:
        await cg.aclose()
        await llama.aclose()
        await fg.aclose()
