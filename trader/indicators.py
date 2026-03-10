"""
Technical indicators — EMA, RSI, ATR, Volume analysis.

All functions operate on pandas DataFrames with standard OHLCV columns.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential Moving Average."""
    return series.ewm(span=period, adjust=False).mean()


def sma(series: pd.Series, period: int) -> pd.Series:
    """Simple Moving Average."""
    return series.rolling(window=period).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index (Wilder's smoothing)."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range."""
    high = df["high"]
    low = df["low"]
    close = df["close"].shift(1)
    tr = pd.concat([
        high - low,
        (high - close).abs(),
        (low - close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def volume_ratio(df: pd.DataFrame, period: int = 20) -> float:
    """Current volume relative to average over *period* candles.

    Returns >1 if above average, <1 if below.
    """
    vol = df["volume"]
    avg = vol.iloc[-period - 1:-1].mean()
    if avg == 0:
        return 1.0
    return float(vol.iloc[-1] / avg)


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add all indicators as columns to the DataFrame."""
    df = df.copy()
    df["ema9"] = ema(df["close"], 9)
    df["ema21"] = ema(df["close"], 21)
    df["ema50"] = ema(df["close"], 50)
    df["rsi"] = rsi(df["close"], 14)
    df["atr"] = atr(df, 14)
    df["vol_sma"] = sma(df["volume"], 20)
    return df
