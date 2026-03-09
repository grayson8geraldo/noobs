"""
Trading engine — orchestrates the full cycle:
  fetch data → analyse → generate signals → size position → execute.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import ccxt

from .candle_analysis import Trend, analyze_candles
from .exchange import fetch_ohlcv, get_balance, place_market_order, set_leverage
from .risk import PositionPlan, size_position
from .round_levels import compute_round_levels, nearest_levels
from .signals import Signal, generate_signals

log = logging.getLogger("trader")

# Map timeframe strings to minutes
_TF_MINUTES = {
    "1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30,
    "1h": 60, "2h": 120, "4h": 240, "1d": 1440, "1w": 10080,
}


@dataclass
class TradeResult:
    signal: Signal
    plan: PositionPlan
    order: dict | None
    error: str | None = None


def run_once(
    exchange: ccxt.Exchange,
    symbol: str,
    timeframe: str,
    risk_pct: float,
    max_leverage: float,
    dry_run: bool = True,
) -> list[TradeResult]:
    """Run a single analysis + trade cycle.

    Parameters
    ----------
    dry_run : bool
        If True, do NOT place real orders — only log what would happen.
    """
    tf_min = _TF_MINUTES.get(timeframe, 15)

    # 1. Fetch candles
    df = fetch_ohlcv(exchange, symbol, timeframe=timeframe, limit=100)
    price = float(df["close"].iloc[-1])
    log.info("Symbol=%s  Price=%.2f  TF=%s", symbol, price, timeframe)

    # 2. Candle trend
    stats = analyze_candles(df)
    log.info(
        "Trend=%s  Bulls=%d (%.1f)  Bears=%d (%.1f)  Ratio=%.2f",
        stats.trend.value,
        stats.bull_count, stats.bull_body_sum,
        stats.bear_count, stats.bear_body_sum,
        stats.dominance_ratio,
    )

    # 3. Round levels
    levels = compute_round_levels(price, timeframe_minutes=tf_min)
    support, resistance = nearest_levels(price, levels)
    log.info(
        "Support=%s  Resistance=%s",
        f"{support.price}" if support else "-",
        f"{resistance.price}" if resistance else "-",
    )

    # 4. Signals
    signals = generate_signals(df, timeframe_minutes=tf_min)
    if not signals:
        log.info("No trade signal — standing aside.")
        return []

    # 5. Size & (optionally) execute
    equity = get_balance(exchange) if not dry_run else 100.0
    results: list[TradeResult] = []

    for sig in signals:
        log.info("SIGNAL %s | %s", sig.direction, sig.reason)

        plan = size_position(
            equity=equity,
            entry=sig.entry,
            stop_loss=sig.stop_loss,
            take_profit=sig.take_profit,
            risk_pct=risk_pct,
            max_leverage=max_leverage,
        )
        log.info(
            "Plan: side=%s  qty=%.6f  lev=%.1fx  risk=$%.2f  R:R=%.1f",
            plan.side, plan.quantity, plan.leverage, plan.risk_amount, plan.risk_reward,
        )

        order = None
        error = None
        if not dry_run:
            try:
                set_leverage(exchange, symbol, int(plan.leverage))
                order = place_market_order(
                    exchange, symbol,
                    side="buy" if plan.side == "long" else "sell",
                    quantity=plan.quantity,
                    stop_loss=plan.stop_loss,
                    take_profit=plan.take_profit,
                )
                log.info("Order placed: %s", order.get("id"))
            except Exception as exc:
                error = str(exc)
                log.error("Order failed: %s", error)
        else:
            log.info("[DRY RUN] Order would be placed.")

        results.append(TradeResult(signal=sig, plan=plan, order=order, error=error))

    return results


def run_loop(
    exchange: ccxt.Exchange,
    symbol: str,
    timeframe: str,
    risk_pct: float,
    max_leverage: float,
    dry_run: bool = True,
) -> None:
    """Run the trading loop continuously, sleeping between candle closes."""
    tf_seconds = _TF_MINUTES.get(timeframe, 15) * 60
    log.info("Starting loop — TF=%s  interval=%ds  dry_run=%s", timeframe, tf_seconds, dry_run)

    while True:
        try:
            run_once(exchange, symbol, timeframe, risk_pct, max_leverage, dry_run)
        except Exception:
            log.exception("Cycle error")
        time.sleep(tf_seconds)
