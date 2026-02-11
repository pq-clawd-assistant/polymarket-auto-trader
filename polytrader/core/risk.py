from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RiskState:
    bankroll_usd: float
    daily_pnl_usd: float = 0.0
    open_positions: int = 0


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def kelly_fraction(p: float, price: float) -> float:
    """Binary contract paying $1 if YES. If buying YES at price, b=(1-price)/price, q=1-p.
    Kelly f* = (bp - q)/b.
    """
    price = clamp(price, 1e-6, 1 - 1e-6)
    b = (1 - price) / price
    q = 1 - p
    f = (b * p - q) / b
    return max(0.0, f)
