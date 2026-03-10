"""
Trading engine — orchestrates the full cycle:
  fetch data → analyse → generate signals → size position → execute.

Supports scanning multiple symbols per cycle and picking the best signal.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import List

import ccxt

from .candle_analysis import Trend, analyze_candles
from .exchange import fetch_ohlcv, fetch_price, get_balance, place_market_order, set_leverage
from .paper_wallet import PaperWallet
from .risk import PositionPlan, RiskProfile, size_position, get_profile, DEFAULT_PROFILE
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
    symbol: str
    signal: Signal
    plan: PositionPlan
    order: dict | None
    error: str | None = None


def _scan_symbol(
    exchange: ccxt.Exchange,
    symbol: str,
    timeframe: str,
    tf_min: int,
) -> tuple[str, float, list[Signal]]:
    """Fetch data and generate signals for a single symbol."""
    df = fetch_ohlcv(exchange, symbol, timeframe=timeframe, limit=100)
    price = float(df["close"].iloc[-1])

    stats = analyze_candles(df)
    signals = generate_signals(df, timeframe_minutes=tf_min)

    log.info(
        "  %-12s  Price=%10.2f  Trend=%-8s  Ratio=%.2f  Signals=%d",
        symbol, price, stats.trend.value, stats.dominance_ratio, len(signals),
    )
    return symbol, price, signals


def run_once(
    exchange: ccxt.Exchange,
    symbols: list[str],
    timeframe: str,
    profile: RiskProfile,
    dry_run: bool = True,
    wallet: PaperWallet | None = None,
) -> list[TradeResult]:
    """Run a single analysis + trade cycle across all symbols.

    Scans every symbol, collects signals, filters by min R:R from profile,
    picks the best one, and executes it.
    """
    tf_min = _TF_MINUTES.get(timeframe, 15)
    paper_mode = wallet is not None

    # 1a. Check open paper positions against current prices
    if paper_mode and wallet.has_open_position:
        for pos in wallet.open_positions:
            try:
                current_price = fetch_price(exchange, pos.symbol)
                log.info(
                    "SL/TP check #%d %s %s | price=%.4f | SL=%.4f TP=%.4f",
                    pos.id, pos.side.upper(), pos.symbol,
                    current_price, pos.stop_loss, pos.take_profit,
                )
                closed = wallet.check_and_close(current_price, symbol=pos.symbol)
                for t in closed:
                    log.info(
                        "Paper #%d %s closed @ %.2f → P&L $%.2f",
                        t.id, t.symbol, t.exit_price, t.pnl,
                    )
            except Exception as exc:
                log.warning("Failed to check price for %s: %s", pos.symbol, exc)

    # 2. Scan all symbols
    log.info("Scanning %d symbols (TF=%s, profile=%s):", len(symbols), timeframe, profile.name)
    all_signals: list[tuple[str, Signal]] = []

    for symbol in symbols:
        try:
            sym, price, sigs = _scan_symbol(exchange, symbol, timeframe, tf_min)
            for sig in sigs:
                all_signals.append((sym, sig))
        except Exception as exc:
            log.warning("  %-12s  SKIP — %s", symbol, exc)

    if not all_signals:
        log.info("No signals across %d symbols — standing aside.", len(symbols))
        return []

    # Skip if already in a paper position
    if paper_mode and wallet.has_open_position:
        log.info("Paper position already open — skipping %d new signal(s).", len(all_signals))
        return []

    # 3. Determine equity
    if paper_mode:
        equity = wallet.balance
    elif not dry_run:
        equity = get_balance(exchange)
    else:
        equity = 100.0

    if equity <= 0:
        log.warning("Zero or negative equity ($%.2f) — cannot trade.", equity)
        return []

    # 4. Size positions, filter by min R:R from profile
    ranked: list[tuple[str, Signal, PositionPlan]] = []
    skipped_rr = 0
    for sym, sig in all_signals:
        try:
            plan = size_position(
                equity=equity,
                entry=sig.entry,
                stop_loss=sig.stop_loss,
                take_profit=sig.take_profit,
                risk_pct=profile.risk_pct,
                max_leverage=profile.max_leverage,
            )
            if plan.risk_reward < profile.min_rr:
                skipped_rr += 1
                continue
            ranked.append((sym, sig, plan))
        except ValueError:
            continue

    if skipped_rr:
        log.info("Filtered out %d signal(s) with R:R < %.1f", skipped_rr, profile.min_rr)

    if not ranked:
        log.info("No signals pass min R:R filter (%.1f).", profile.min_rr)
        return []

    # Sort by risk:reward descending — best trade first
    ranked.sort(key=lambda x: x[2].risk_reward, reverse=True)
    best_sym, best_sig, best_plan = ranked[0]

    log.info(
        "BEST SIGNAL: %s %s | R:R=%.1f | %s",
        best_sym, best_sig.direction, best_plan.risk_reward, best_sig.reason,
    )
    log.info(
        "Plan: side=%s  qty=%.6f  lev=%.1fx  risk=$%.2f (%.0f%% of $%.2f)",
        best_plan.side, best_plan.quantity, best_plan.leverage,
        best_plan.risk_amount, profile.risk_pct, equity,
    )

    if len(ranked) > 1:
        log.info("(%d other signal(s) skipped — lower R:R)", len(ranked) - 1)

    # 5. Execute the best signal
    order = None
    error = None

    if paper_mode:
        trade = wallet.open_trade(
            symbol=best_sym,
            side=best_plan.side,
            entry_price=best_sig.entry,
            quantity=best_plan.quantity,
            leverage=best_plan.leverage,
            stop_loss=best_sig.stop_loss,
            take_profit=best_sig.take_profit,
        )
        order = {"id": f"paper-{trade.id}", "status": "open", "paper": True}
        log.info("[PAPER] Trade #%d on %s opened. Balance: $%.2f", trade.id, best_sym, wallet.balance)
    elif not dry_run:
        try:
            set_leverage(exchange, best_sym, int(best_plan.leverage))
            order = place_market_order(
                exchange, best_sym,
                side="buy" if best_plan.side == "long" else "sell",
                quantity=best_plan.quantity,
                stop_loss=best_plan.stop_loss,
                take_profit=best_plan.take_profit,
            )
            log.info("Order placed: %s", order.get("id"))
        except Exception as exc:
            error = str(exc)
            log.error("Order failed: %s", error)
    else:
        log.info("[DRY RUN] Would open %s %s on %s", best_plan.side, best_sym, best_sig.direction)

    return [TradeResult(
        symbol=best_sym, signal=best_sig, plan=best_plan, order=order, error=error,
    )]


def run_loop(
    exchange: ccxt.Exchange,
    symbols: list[str],
    timeframe: str,
    profile: RiskProfile,
    dry_run: bool = True,
    wallet: PaperWallet | None = None,
) -> None:
    """Run the trading loop continuously, sleeping between candle closes."""
    tf_seconds = _TF_MINUTES.get(timeframe, 15) * 60
    paper_mode = wallet is not None
    mode_label = "PAPER" if paper_mode else ("LIVE" if not dry_run else "DRY RUN")
    log.info(
        "Starting loop — %d symbols  TF=%s  interval=%ds  mode=%s  profile=%s",
        len(symbols), timeframe, tf_seconds, mode_label, profile.name,
    )

    while True:
        try:
            run_once(exchange, symbols, timeframe, profile, dry_run, wallet)

            if paper_mode:
                wallet.print_dashboard()
        except Exception:
            log.exception("Cycle error")

        time.sleep(tf_seconds)
