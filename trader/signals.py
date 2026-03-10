"""
Signal generator — multi-confirmation scoring system.

Entry requires alignment of:
  1. EMA trend (9 > 21 > 50 for longs, inverted for shorts)
  2. RSI confirmation (not overbought for longs, not oversold for shorts)
  3. Price pullback to EMA 21 (buy the dip, not the top)
  4. Round level support/resistance nearby
  5. Volume above average

Each condition adds to a signal score. Minimum score required to trade.

Stop-loss is ATR-based (dynamic, adapts to volatility).
Take-profit targets nearest round level OR 2-3× ATR from entry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

import pandas as pd

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
    level: RoundLevel | None
    trend: object  # kept for compatibility
    reason: str
    score: int = 0  # confirmation count (higher = stronger)
    atr_value: float = 0.0
    confirmations: list[str] = field(default_factory=list)


def _ema_trend_up(df: pd.DataFrame) -> bool:
    """EMA 9 > 21 > 50 — bullish alignment."""
    row = df.iloc[-1]
    return row["ema9"] > row["ema21"] > row["ema50"]


def _ema_trend_down(df: pd.DataFrame) -> bool:
    """EMA 9 < 21 < 50 — bearish alignment."""
    row = df.iloc[-1]
    return row["ema9"] < row["ema21"] < row["ema50"]


def _ema_slope_up(df: pd.DataFrame, period: int = 5) -> bool:
    """EMA 50 is rising over last *period* bars."""
    vals = df["ema50"].iloc[-period:]
    return float(vals.iloc[-1]) > float(vals.iloc[0])


def _ema_slope_down(df: pd.DataFrame, period: int = 5) -> bool:
    """EMA 50 is falling over last *period* bars."""
    vals = df["ema50"].iloc[-period:]
    return float(vals.iloc[-1]) < float(vals.iloc[0])


def _pullback_to_ema(df: pd.DataFrame, direction: str) -> bool:
    """Price pulled back near EMA 21 (within 0.5× ATR).

    For LONG: price dipped close to EMA 21 from above.
    For SHORT: price rallied close to EMA 21 from below.
    """
    row = df.iloc[-1]
    atr_val = row["atr"]
    price = row["close"]
    ema21 = row["ema21"]

    if atr_val == 0:
        return False

    distance = abs(price - ema21) / atr_val

    if direction == "LONG":
        # Price should be near or just above EMA 21
        return distance < 1.5 and price >= ema21 * 0.995
    else:
        # Price should be near or just below EMA 21
        return distance < 1.5 and price <= ema21 * 1.005


def generate_signals(
    df: pd.DataFrame,
    timeframe_minutes: int = 15,
    candle_lookback: int = 20,
    dominance_threshold: float = 1.3,
    zone_pct: float = 0.5,
    min_score: int = 3,
    atr_sl_mult: float = 1.5,
    atr_tp_mult: float = 3.0,
) -> List[Signal]:
    """Generate signals using multi-confirmation scoring.

    Parameters
    ----------
    min_score : int
        Minimum number of confirmations to generate a signal.
    atr_sl_mult : float
        ATR multiplier for stop-loss distance.
    atr_tp_mult : float
        ATR multiplier for take-profit distance (fallback).
    """
    if len(df) < 55:  # need enough data for EMA 50
        return []

    df = compute_indicators(df)
    price = float(df["close"].iloc[-1])
    atr_val = float(df["atr"].iloc[-1])

    if atr_val == 0:
        return []

    levels = compute_round_levels(price, timeframe_minutes=timeframe_minutes, zone_pct=zone_pct)
    support, resistance = nearest_levels(price, levels)
    in_zone = price_in_zone(price, levels)
    vol_ratio = volume_ratio(df)

    rsi_val = float(df["rsi"].iloc[-1])

    signals: List[Signal] = []

    # ── LONG signal scoring ──────────────────────────────────────────────
    long_score = 0
    long_confirms: list[str] = []

    # 1. EMA trend alignment (strongest confirmation)
    if _ema_trend_up(df):
        long_score += 2
        long_confirms.append("EMA 9>21>50 aligned bullish")
    elif _ema_slope_up(df):
        long_score += 1
        long_confirms.append("EMA50 slope up")

    # 2. RSI not overbought + in bullish zone
    if 35 <= rsi_val <= 65:
        long_score += 1
        long_confirms.append(f"RSI neutral ({rsi_val:.0f})")
    elif rsi_val < 35:
        long_score += 2
        long_confirms.append(f"RSI oversold ({rsi_val:.0f})")

    # 3. Pullback to EMA 21 (buy the dip)
    if _pullback_to_ema(df, "LONG"):
        long_score += 1
        long_confirms.append("Pullback to EMA21")

    # 4. Round level support nearby
    if support is not None:
        dist_to_support = (price - support.price) / price
        if dist_to_support < 0.02:  # within 2%
            long_score += 1
            long_confirms.append(f"Support at {support.price}")
            if in_zone is not None and in_zone.price <= price:
                long_score += 1
                long_confirms.append("In support zone")

    # 5. Volume confirmation
    if vol_ratio > 1.2:
        long_score += 1
        long_confirms.append(f"Volume {vol_ratio:.1f}x avg")

    # Generate LONG if enough confirmations
    if long_score >= min_score and rsi_val < 75:
        sl = price - atr_val * atr_sl_mult

        # Use round level support as SL floor if it's tighter than ATR
        if support is not None and support.zone_low > sl:
            sl = support.zone_low - atr_val * 0.3  # small buffer below zone

        # TP: nearest resistance or ATR-based
        if resistance is not None and resistance.price > price:
            tp = resistance.price
            # But ensure minimum R:R of 1.5
            sl_dist = price - sl
            tp_dist = tp - price
            if sl_dist > 0 and tp_dist / sl_dist < 1.5:
                tp = price + atr_val * atr_tp_mult
        else:
            tp = price + atr_val * atr_tp_mult

        signals.append(Signal(
            direction="LONG",
            entry=price,
            stop_loss=round(sl, 6),
            take_profit=round(tp, 6),
            level=support,
            trend=None,
            score=long_score,
            atr_value=atr_val,
            confirmations=long_confirms,
            reason=f"LONG score={long_score}: {'; '.join(long_confirms)}",
        ))

    # ── SHORT signal scoring ─────────────────────────────────────────────
    short_score = 0
    short_confirms: list[str] = []

    # 1. EMA trend alignment
    if _ema_trend_down(df):
        short_score += 2
        short_confirms.append("EMA 9<21<50 aligned bearish")
    elif _ema_slope_down(df):
        short_score += 1
        short_confirms.append("EMA50 slope down")

    # 2. RSI not oversold + in bearish zone
    if 35 <= rsi_val <= 65:
        short_score += 1
        short_confirms.append(f"RSI neutral ({rsi_val:.0f})")
    elif rsi_val > 65:
        short_score += 2
        short_confirms.append(f"RSI overbought ({rsi_val:.0f})")

    # 3. Pullback to EMA 21 (sell the rally)
    if _pullback_to_ema(df, "SHORT"):
        short_score += 1
        short_confirms.append("Rally to EMA21")

    # 4. Round level resistance nearby
    if resistance is not None:
        dist_to_resistance = (resistance.price - price) / price
        if dist_to_resistance < 0.02:
            short_score += 1
            short_confirms.append(f"Resistance at {resistance.price}")
            if in_zone is not None and in_zone.price >= price:
                short_score += 1
                short_confirms.append("In resistance zone")

    # 5. Volume confirmation
    if vol_ratio > 1.2:
        short_score += 1
        short_confirms.append(f"Volume {vol_ratio:.1f}x avg")

    # Generate SHORT if enough confirmations
    if short_score >= min_score and rsi_val > 25:
        sl = price + atr_val * atr_sl_mult

        if resistance is not None and resistance.zone_high < sl:
            sl = resistance.zone_high + atr_val * 0.3

        if support is not None and support.price < price:
            tp = support.price
            sl_dist = sl - price
            tp_dist = price - tp
            if sl_dist > 0 and tp_dist / sl_dist < 1.5:
                tp = price - atr_val * atr_tp_mult
        else:
            tp = price - atr_val * atr_tp_mult

        signals.append(Signal(
            direction="SHORT",
            entry=price,
            stop_loss=round(sl, 6),
            take_profit=round(tp, 6),
            level=resistance,
            trend=None,
            score=short_score,
            atr_value=atr_val,
            confirmations=short_confirms,
            reason=f"SHORT score={short_score}: {'; '.join(short_confirms)}",
        ))

    return signals
