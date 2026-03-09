"""
Candlestick Trend Analysis — visual dominance of bulls vs bears.

Rules
-----
* Compare the total body size of green (bullish) candles to red (bearish)
  candles over a lookback window.
* If bulls dominate in both count AND cumulative body size → uptrend.
* If bears dominate → downtrend.
* Otherwise → sideways / uncertain — stay out.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List

import numpy as np
import pandas as pd


class Trend(Enum):
    UP = "UP"
    DOWN = "DOWN"
    SIDEWAYS = "SIDEWAYS"


@dataclass
class CandleStats:
    trend: Trend
    bull_count: int
    bear_count: int
    bull_body_sum: float
    bear_body_sum: float
    dominance_ratio: float  # >1 bulls dominate, <1 bears dominate


def analyze_candles(
    df: pd.DataFrame,
    lookback: int = 20,
    dominance_threshold: float = 1.3,
) -> CandleStats:
    """Determine trend direction via candlestick body dominance.

    Parameters
    ----------
    df : pd.DataFrame
        OHLCV dataframe with columns: open, high, low, close, volume.
        Most recent candle is the last row.
    lookback : int
        Number of recent candles to evaluate.
    dominance_threshold : float
        Minimum ratio of winning side's total body to losing side's total body
        to declare a clear trend. Below this → SIDEWAYS.
    """
    window = df.tail(lookback).copy()

    bodies = (window["close"] - window["open"]).values
    bull_mask = bodies > 0
    bear_mask = bodies < 0

    bull_count = int(np.sum(bull_mask))
    bear_count = int(np.sum(bear_mask))
    bull_body = float(np.sum(np.abs(bodies[bull_mask])))
    bear_body = float(np.sum(np.abs(bodies[bear_mask])))

    if bear_body == 0 and bull_body == 0:
        ratio = 1.0
    elif bear_body == 0:
        ratio = float("inf")
    else:
        ratio = bull_body / bear_body

    if ratio >= dominance_threshold and bull_count > bear_count:
        trend = Trend.UP
    elif ratio <= 1 / dominance_threshold and bear_count > bull_count:
        trend = Trend.DOWN
    else:
        trend = Trend.SIDEWAYS

    return CandleStats(
        trend=trend,
        bull_count=bull_count,
        bear_count=bear_count,
        bull_body_sum=bull_body,
        bear_body_sum=bear_body,
        dominance_ratio=round(ratio, 3),
    )


def multi_timeframe_trend(
    dfs: dict[str, pd.DataFrame],
    lookback: int = 20,
    dominance_threshold: float = 1.3,
) -> dict[str, CandleStats]:
    """Run candle analysis on several timeframe DataFrames at once."""
    return {
        tf: analyze_candles(frame, lookback, dominance_threshold)
        for tf, frame in dfs.items()
    }
