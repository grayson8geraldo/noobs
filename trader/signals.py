"""
Signal generator — combines Round Levels + Candle Analysis into trade signals,
enhanced with EMA trend filter, RSI confirmation, and ATR-based stops.

Entry logic
-----------
1. Price approaches or bounces off a strong round level.
2. Candle analysis confirms the expected trend direction.
3. EMA trend filter must agree with the direction.
4. RSI must not be extreme against the trade.
5. Stop-loss is ATR-based (adapts to volatility) instead of fixed zone offset.
6. If all conditions align → generate a signal with entry, SL, TP.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

import pandas as pd

from .candle_analysis import CandleStats, Trend, analyze_candles
from .indicators import compute_indicators, volume_ratio
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


def generate_signals(
    df: pd.DataFrame,
    timeframe_minutes: int = 15,
    candle_lookback: int = 20,
    dominance_threshold: float = 1.2,
    zone_pct: float = 0.5,
    atr_sl_mult: float = 1.5,
) -> List[Signal]:
    """Scan current price against round levels, candle trend, EMA, and RSI.

    Improvements over the original:
    - dominance_threshold lowered from 1.3 → 1.2 (catch more valid trends)
    - EMA 21/50 trend filter: only trade in direction of EMA slope
    - RSI guard: skip longs when RSI > 70, shorts when RSI < 30
    - ATR-based SL instead of tiny zone-offset SL
    - Wider proximity to levels: 2% instead of 1%
    """
    if df.empty or len(df) < 55:
        return []

    price = float(df["close"].iloc[-1])
    stats = analyze_candles(df, lookback=candle_lookback, dominance_threshold=dominance_threshold)
    levels = compute_round_levels(price, timeframe_minutes=timeframe_minutes, zone_pct=zone_pct)
    support, resistance = nearest_levels(price, levels)
    in_zone = price_in_zone(price, levels)

    # Compute indicators for additional filters
    df_ind = compute_indicators(df)
    row = df_ind.iloc[-1]
    rsi_val = float(row["rsi"])
    atr_val = float(row["atr"])
    ema21 = float(row["ema21"])
    ema50 = float(row["ema50"])

    if atr_val == 0:
        return []

    signals: List[Signal] = []

    # ── LONG: price at support + bullish candles + EMA/RSI confirm ────
    if stats.trend == Trend.UP and support is not None:
        near_support = (price - support.zone_high) / price < 0.02  # 2% (was 1%)
        at_support = in_zone is not None and in_zone.price <= price

        # EMA filter: price above EMA 50 OR EMA 21 > EMA 50 (uptrend)
        ema_ok = price > ema50 or ema21 > ema50
        # RSI guard: don't buy overbought
        rsi_ok = rsi_val < 70

        if (near_support or at_support) and ema_ok and rsi_ok:
            # ATR-based stop-loss — much wider than zone offset
            sl = price - atr_val * atr_sl_mult

            # But don't place SL above support zone low
            zone_sl = support.zone_low - atr_val * 0.3
            if sl > zone_sl:
                sl = zone_sl

            tp = resistance.price if resistance else price + (price - sl)
            # Ensure minimum R:R of 1.5
            sl_dist = price - sl
            tp_dist = tp - price
            if sl_dist > 0 and tp_dist / sl_dist < 1.5:
                tp = price + sl_dist * 2.0

            signals.append(Signal(
                direction="LONG",
                entry=price,
                stop_loss=round(sl, 6),
                take_profit=round(tp, 6),
                level=support,
                trend=stats,
                reason=(
                    f"Price near support {support.price}; "
                    f"bulls dominate (ratio {stats.dominance_ratio}); "
                    f"RSI={rsi_val:.0f}; EMA21{'>' if ema21 > ema50 else '<'}EMA50"
                ),
            ))

    # ── SHORT: price at resistance + bearish candles + EMA/RSI confirm ─
    if stats.trend == Trend.DOWN and resistance is not None:
        near_resistance = (resistance.zone_low - price) / price < 0.02  # 2%
        at_resistance = in_zone is not None and in_zone.price >= price

        # EMA filter: price below EMA 50 OR EMA 21 < EMA 50 (downtrend)
        ema_ok = price < ema50 or ema21 < ema50
        # RSI guard: don't short oversold
        rsi_ok = rsi_val > 30

        if (near_resistance or at_resistance) and ema_ok and rsi_ok:
            sl = price + atr_val * atr_sl_mult

            zone_sl = resistance.zone_high + atr_val * 0.3
            if sl < zone_sl:
                sl = zone_sl

            tp = support.price if support else price - (sl - price)
            sl_dist = sl - price
            tp_dist = price - tp
            if sl_dist > 0 and tp_dist / sl_dist < 1.5:
                tp = price - sl_dist * 2.0

            signals.append(Signal(
                direction="SHORT",
                entry=price,
                stop_loss=round(sl, 6),
                take_profit=round(tp, 6),
                level=resistance,
                trend=stats,
                reason=(
                    f"Price near resistance {resistance.price}; "
                    f"bears dominate (ratio {stats.dominance_ratio}); "
                    f"RSI={rsi_val:.0f}; EMA21{'>' if ema21 > ema50 else '<'}EMA50"
                ),
            ))

    return signals
