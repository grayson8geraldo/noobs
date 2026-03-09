"""
Round Levels — Support & Resistance based on psychological price levels.

Round numbers ($1000, $5000, $10000, etc.) act as magnets for orders.
The "rounder" the number, the stronger the level.
A level is a zone, not a thin line — price can overshoot or undershoot slightly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List


@dataclass
class RoundLevel:
    """A single round-number level with its strength weight."""
    price: float
    strength: int  # higher = stronger (5 = $10k step, 4 = $5k, 3 = $1k, etc.)
    zone_low: float
    zone_high: float

    @property
    def zone_pct(self) -> float:
        return (self.zone_high - self.zone_low) / self.price * 100


# ── step presets per price magnitude ──────────────────────────────────────────
# (step_value, strength_weight)
_STEP_TABLE = [
    (100_000, 6),
    (50_000,  5),
    (10_000,  5),
    (5_000,   4),
    (1_000,   3),
    (500,     2),
    (100,     2),
    (50,      1),
    (10,      1),
    (5,       1),
    (1,       1),
    (0.5,     1),
    (0.1,     1),
]


def _choose_steps(price: float, timeframe_minutes: int) -> List[tuple]:
    """Pick relevant step sizes depending on current price and timeframe.

    For high-priced assets on small timeframes we include finer steps.
    For weekly charts we only keep the coarsest steps.
    """
    # base range: levels that are between 2% and 200% of current price apart
    min_step = price * 0.005
    max_step = price * 3.0

    # on timeframes <= 15 min allow finer granularity
    if timeframe_minutes <= 15:
        min_step = price * 0.002

    selected = [(s, w) for s, w in _STEP_TABLE if min_step <= s <= max_step]
    return selected if selected else [_STEP_TABLE[-1]]


def compute_round_levels(
    price: float,
    lookback: float | None = None,
    timeframe_minutes: int = 15,
    zone_pct: float = 0.5,
) -> List[RoundLevel]:
    """Return round-number levels surrounding *price*.

    Parameters
    ----------
    price : float
        Current market price.
    lookback : float, optional
        How far above/below current price to scan. Defaults to ±50 % of price.
    timeframe_minutes : int
        Chart timeframe in minutes (affects which steps are relevant).
    zone_pct : float
        Half-width of the zone around each level, in percent of the level price.
    """
    if lookback is None:
        lookback = price * 0.5

    low_bound = price - lookback
    high_bound = price + lookback

    steps = _choose_steps(price, timeframe_minutes)
    seen: set[float] = set()
    levels: List[RoundLevel] = []

    for step, strength in steps:
        first = math.floor(low_bound / step) * step
        lvl = first
        while lvl <= high_bound:
            if lvl > 0 and lvl not in seen:
                half = lvl * zone_pct / 100
                levels.append(RoundLevel(
                    price=lvl,
                    strength=strength,
                    zone_low=lvl - half,
                    zone_high=lvl + half,
                ))
                seen.add(lvl)
            lvl += step

    levels.sort(key=lambda l: l.price)
    return levels


def nearest_levels(
    price: float,
    levels: List[RoundLevel],
) -> tuple[RoundLevel | None, RoundLevel | None]:
    """Return (nearest_support, nearest_resistance) relative to *price*."""
    support: RoundLevel | None = None
    resistance: RoundLevel | None = None

    for lvl in levels:
        if lvl.price < price:
            if support is None or lvl.price > support.price:
                support = lvl
        elif lvl.price > price:
            if resistance is None or lvl.price < resistance.price:
                resistance = lvl

    return support, resistance


def price_in_zone(price: float, levels: List[RoundLevel]) -> RoundLevel | None:
    """Return the level whose zone the price currently sits inside, if any."""
    for lvl in levels:
        if lvl.zone_low <= price <= lvl.zone_high:
            return lvl
    return None
