"""
Trading engine — orchestrates the full cycle:
  fetch data → analyse → generate signals → size position → execute.

Features:
  - Multi-symbol scanning with signal scoring
  - ATR-based trailing stop (moves SL to breakeven after 1R profit)
  - Cooldown after consecutive losses
  - Only takes highest-scoring signals
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import List

import ccxt

from .exchange import fetch_ohlcv, fetch_price, get_balance, place_market_order, set_leverage
from .indicators import compute_indicators
from .paper_wallet import PaperWallet
from .risk import PositionPlan, RiskProfile, size_position
from .signals import Signal, generate_signals

log = logging.getLogger("trader")

# Map timeframe strings to minutes
_TF_MINUTES = {
    "1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30,
    "1h": 60, "2h": 120, "4h": 240, "1d": 1440, "1w": 10080,
}

# Cooldown: skip N cycles after consecutive losses
_MAX_CONSECUTIVE_LOSSES = 3
_COOLDOWN_CYCLES = 2


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

    signals = generate_signals(df, timeframe_minutes=tf_min)

    if signals:
        best = max(signals, key=lambda s: s.score)
        log.info(
            "  %-12s  Price=%10.4f  Signals=%d  Best=%s(score=%d)",
            symbol, price, len(signals), best.direction, best.score,
        )
    else:
        log.debug("  %-12s  Price=%10.4f  No signals", symbol, price)
    return symbol, price, signals


def _check_trailing_stop(wallet: PaperWallet, exchange: ccxt.Exchange) -> None:
    """Move SL to breakeven+fees once price has moved 1× ATR in favor."""
    for pos in wallet.open_positions:
        try:
            current_price = fetch_price(exchange, pos.symbol)
        except Exception:
            continue

        entry = pos.entry_price
        original_sl = pos.stop_loss

        if pos.side == "long":
            # If price moved up significantly, trail SL to breakeven
            profit_pct = (current_price - entry) / entry
            if profit_pct > 0.01:  # > 1% profit
                # Move SL to entry + small buffer (breakeven + fees)
                new_sl = entry * 1.002  # cover fees
                if new_sl > original_sl:
                    pos.stop_loss = round(new_sl, 6)
                    log.info(
                        "TRAIL #%d %s SL moved: %.4f → %.4f (breakeven)",
                        pos.id, pos.symbol, original_sl, pos.stop_loss,
                    )
        else:  # short
            profit_pct = (entry - current_price) / entry
            if profit_pct > 0.01:
                new_sl = entry * 0.998
                if new_sl < original_sl:
                    pos.stop_loss = round(new_sl, 6)
                    log.info(
                        "TRAIL #%d %s SL moved: %.4f → %.4f (breakeven)",
                        pos.id, pos.symbol, original_sl, pos.stop_loss,
                    )


def _recent_consecutive_losses(wallet: PaperWallet) -> int:
    """Count consecutive losses from the most recent closed trades."""
    closed = wallet.closed_trades
    if not closed:
        return 0
    count = 0
    for t in reversed(closed):
        if t.pnl <= 0:
            count += 1
        else:
            break
    return count


def run_once(
    exchange: ccxt.Exchange,
    symbols: list[str],
    timeframe: str,
    profile: RiskProfile,
    dry_run: bool = True,
    wallet: PaperWallet | None = None,
) -> list[TradeResult]:
    """Run a single analysis + trade cycle across all symbols."""
    tf_min = _TF_MINUTES.get(timeframe, 15)
    paper_mode = wallet is not None

    # 1a. Check open paper positions — trailing stop + SL/TP
    if paper_mode and wallet.has_open_position:
        _check_trailing_stop(wallet, exchange)

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
                    result_tag = "WIN" if t.pnl > 0 else "LOSS"
                    log.info(
                        "Paper #%d %s closed @ %.4f → P&L $%.2f [%s]",
                        t.id, t.symbol, t.exit_price, t.pnl, result_tag,
                    )
            except Exception as exc:
                log.warning("Failed to check price for %s: %s", pos.symbol, exc)

    # 1b. Cooldown check after consecutive losses
    if paper_mode:
        consec_losses = _recent_consecutive_losses(wallet)
        if consec_losses >= _MAX_CONSECUTIVE_LOSSES:
            log.warning(
                "Cooldown: %d consecutive losses — skipping this cycle. "
                "Will resume after %d idle cycles.",
                consec_losses, _COOLDOWN_CYCLES,
            )
            return []

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

    # 4. Size positions, filter by min R:R, sort by score then R:R
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

    # Sort by signal score (primary), then R:R (secondary)
    ranked.sort(key=lambda x: (x[1].score, x[2].risk_reward), reverse=True)
    best_sym, best_sig, best_plan = ranked[0]

    log.info(
        "BEST SIGNAL: %s %s | Score=%d R:R=%.1f | %s",
        best_sym, best_sig.direction, best_sig.score, best_plan.risk_reward, best_sig.reason,
    )
    log.info(
        "Plan: side=%s  qty=%.6f  lev=%.1fx  risk=$%.2f (%.0f%% of $%.2f)",
        best_plan.side, best_plan.quantity, best_plan.leverage,
        best_plan.risk_amount, profile.risk_pct, equity,
    )

    if len(ranked) > 1:
        log.info("(%d other signal(s) skipped — lower score/R:R)", len(ranked) - 1)

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

    cooldown_remaining = 0

    while True:
        try:
            if cooldown_remaining > 0:
                cooldown_remaining -= 1
                log.info("Cooldown: %d cycle(s) remaining — watching positions only.", cooldown_remaining)
                # Still check open positions during cooldown
                if paper_mode and wallet.has_open_position:
                    _check_trailing_stop(wallet, exchange)
                    for pos in wallet.open_positions:
                        try:
                            current_price = fetch_price(exchange, pos.symbol)
                            wallet.check_and_close(current_price, symbol=pos.symbol)
                        except Exception:
                            pass
            else:
                results = run_once(exchange, symbols, timeframe, profile, dry_run, wallet)

                # Check if we need to enter cooldown
                if paper_mode and not results:
                    consec = _recent_consecutive_losses(wallet)
                    if consec >= _MAX_CONSECUTIVE_LOSSES:
                        cooldown_remaining = _COOLDOWN_CYCLES

            if paper_mode:
                wallet.print_dashboard()
        except Exception:
            log.exception("Cycle error")

        time.sleep(tf_seconds)
