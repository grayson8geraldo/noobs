"""
Signal generator — combines Round Levels + Candle Analysis into trade signals.

Entry logic
-----------
1. Price approaches or bounces off a strong round level.
2. Candle analysis confirms the expected trend direction.
3. If both conditions align → generate a signal with entry, SL, TP.

LONG signal:
  - Price is in the zone of a support level (or just bounced up from it).
  - Candle analysis shows UP trend (bulls dominate).
  - SL = below the support zone.
  - TP = next resistance level.

SHORT signal:
  - Price is in the zone of a resistance level (or just bounced down from it).
  - Candle analysis shows DOWN trend (bears dominate).
  - SL = above the resistance zone.
  - TP = next support level.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

import pandas as pd

from .candle_analysis import CandleStats, Trend, analyze_candles
from .round_levels import (
    RoundLevel,
    compute_round_levels,
    nearest_levels,
    price_in_zone,
)


@dataclass
class Signal:
    direction: str  # "LONG" or "SHORT"
    entry: float
    stop_loss: float
    take_profit: float
    level: RoundLevel
    trend: CandleStats
    reason: str


def _sl_offset(level: RoundLevel) -> float:
    """Extra margin beyond the zone for the stop-loss."""
    return (level.zone_high - level.zone_low) * 0.5


def generate_signals(
    df: pd.DataFrame,
    timeframe_minutes: int = 15,
    candle_lookback: int = 20,
    dominance_threshold: float = 1.3,
    zone_pct: float = 0.5,
) -> List[Signal]:
    """Scan current price against round levels and candle trend."""
    if df.empty:
        return []

    price = float(df["close"].iloc[-1])
    stats = analyze_candles(df, lookback=candle_lookback, dominance_threshold=dominance_threshold)
    levels = compute_round_levels(price, timeframe_minutes=timeframe_minutes, zone_pct=zone_pct)
    support, resistance = nearest_levels(price, levels)
    in_zone = price_in_zone(price, levels)

    signals: List[Signal] = []

    # ── LONG: price at support + bullish candles ──────────────────────────
    if stats.trend == Trend.UP and support is not None:
        near_support = (price - support.zone_high) / price < 0.01  # within 1%
        at_support = in_zone is not None and in_zone.price <= price

        if near_support or at_support:
            sl = support.zone_low - _sl_offset(support)
            tp = resistance.price if resistance else price + (price - sl)
            signals.append(Signal(
                direction="LONG",
                entry=price,
                stop_loss=round(sl, 2),
                take_profit=round(tp, 2),
                level=support,
                trend=stats,
                reason=(
                    f"Price near support {support.price}; "
                    f"bulls dominate (ratio {stats.dominance_ratio})"
                ),
            ))

    # ── SHORT: price at resistance + bearish candles ─────────────────────
    if stats.trend == Trend.DOWN and resistance is not None:
        near_resistance = (resistance.zone_low - price) / price < 0.01
        at_resistance = in_zone is not None and in_zone.price >= price

        if near_resistance or at_resistance:
            sl = resistance.zone_high + _sl_offset(resistance)
            tp = support.price if support else price - (sl - price)
            signals.append(Signal(
                direction="SHORT",
                entry=price,
                stop_loss=round(sl, 2),
                take_profit=round(tp, 2),
                level=resistance,
                trend=stats,
                reason=(
                    f"Price near resistance {resistance.price}; "
                    f"bears dominate (ratio {stats.dominance_ratio})"
                ),
            ))

    return signals
