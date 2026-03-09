#!/usr/bin/env python3
"""
Crypto Futures Trader — small deposit accelerator.

Strategy:
  1. Round-number support/resistance levels
  2. Candlestick trend analysis (bull vs bear dominance)
  3. Risk-managed position sizing

Usage:
  python main.py paper                            # paper trading $150→$1000
  python main.py paper --symbol ETH/USDT          # paper trade ETH
  python main.py paper --balance 200 --target 2000 # custom goal
  python main.py paper --status                    # show dashboard
  python main.py --once                            # dry-run single cycle
  python main.py --live                            # live trading (real orders)
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from trader.config import Config
from trader.exchange import create_exchange
from trader.engine import run_loop, run_once
from trader.paper_wallet import PaperWallet
from trader.symbols import resolve_symbols, PRESETS


def cmd_paper(args: argparse.Namespace, cfg: Config) -> None:
    """Paper trading mode — real data, virtual balance."""
    log = logging.getLogger("main")

    state_file = args.state_file or "paper_state.json"

    if args.reset:
        wallet = PaperWallet(
            initial_balance=args.balance,
            balance=args.balance,
            target=args.target,
            target_days=args.days,
            _state_file=state_file,
        )
        wallet.save()
        log.info("Paper wallet reset: $%.2f → target $%.2f in %d days", wallet.balance, wallet.target, wallet.target_days)
    else:
        if os.path.exists(state_file):
            wallet = PaperWallet.load(state_file)
            log.info("Resumed paper wallet: $%.2f (started at $%.2f)", wallet.balance, wallet.initial_balance)
        else:
            wallet = PaperWallet(
                initial_balance=args.balance,
                balance=args.balance,
                target=args.target,
                target_days=args.days,
                _state_file=state_file,
            )
            wallet.save()
            log.info("New paper wallet: $%.2f → target $%.2f in %d days", wallet.balance, wallet.target, wallet.target_days)

    # Show status and exit
    if args.status:
        wallet.print_dashboard()
        return

    # Apply CLI overrides to config
    if args.symbols:
        cfg.symbols = resolve_symbols(args.symbols)
    if args.symbol:
        cfg.symbols = [args.symbol]
    if args.timeframe:
        cfg.timeframe = args.timeframe
    if args.risk:
        cfg.risk_pct = args.risk
    if args.leverage:
        cfg.max_leverage = args.leverage

    log.info("=== PAPER TRADING MODE ===")
    log.info("Exchange : %s (public data only, no API keys needed)", cfg.exchange_id)
    log.info("Symbols  : %d pairs", len(cfg.symbols))
    log.info("Timeframe: %s", cfg.timeframe)
    log.info("Risk     : %.1f%%", cfg.risk_pct)
    log.info("Leverage : max %.0fx", cfg.max_leverage)
    log.info("Balance  : $%.2f → Target: $%.2f in %d days", wallet.balance, wallet.target, wallet.target_days)

    # Connect to exchange (public endpoints only)
    exchange = create_exchange(cfg.exchange_id, public_only=True)

    wallet.print_dashboard()

    if args.once:
        results = run_once(
            exchange, cfg.symbols, cfg.timeframe,
            cfg.risk_pct, cfg.max_leverage,
            dry_run=True, wallet=wallet,
        )
        wallet.print_dashboard()
        if not results:
            log.info("No signals generated.")
    else:
        run_loop(
            exchange, cfg.symbols, cfg.timeframe,
            cfg.risk_pct, cfg.max_leverage,
            dry_run=True, wallet=wallet,
        )


def cmd_trade(args: argparse.Namespace, cfg: Config) -> None:
    """Live / dry-run trading mode."""
    log = logging.getLogger("main")

    if args.symbols:
        cfg.symbols = resolve_symbols(args.symbols)
    if args.symbol:
        cfg.symbols = [args.symbol]
    if args.timeframe:
        cfg.timeframe = args.timeframe
    if args.risk:
        cfg.risk_pct = args.risk
    if args.leverage:
        cfg.max_leverage = args.leverage
    cfg.dry_run = not args.live

    log.info("=== Crypto Futures Trader ===")
    log.info("Exchange : %s", cfg.exchange_id)
    log.info("Symbols  : %d pairs", len(cfg.symbols))
    log.info("Timeframe: %s", cfg.timeframe)
    log.info("Risk     : %.1f%%", cfg.risk_pct)
    log.info("Leverage : max %.0fx", cfg.max_leverage)
    log.info("Mode     : %s", "LIVE" if not cfg.dry_run else "DRY RUN")

    if cfg.dry_run and (not cfg.api_key or not cfg.api_secret):
        log.warning("No API keys found — running in dry-run mode with demo data.")

    exchange = create_exchange(cfg.exchange_id, cfg.api_key, cfg.api_secret)

    if args.once:
        results = run_once(
            exchange, cfg.symbols, cfg.timeframe,
            cfg.risk_pct, cfg.max_leverage, cfg.dry_run,
        )
        if not results:
            log.info("No signals generated.")
        for r in results:
            if r.error:
                log.error("Trade error: %s", r.error)
    else:
        run_loop(
            exchange, cfg.symbols, cfg.timeframe,
            cfg.risk_pct, cfg.max_leverage, cfg.dry_run,
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Crypto Futures Trader — small deposit accelerator",
    )
    parser.add_argument("--env", type=str, default=".env", help="Path to .env file")
    subparsers = parser.add_subparsers(dest="command")

    # ── paper subcommand ─────────────────────────────────────────────────
    p_paper = subparsers.add_parser("paper", help="Paper trading with virtual balance")
    p_paper.add_argument("--balance", type=float, default=150.0, help="Starting balance (default: $150)")
    p_paper.add_argument("--target", type=float, default=1000.0, help="Target balance (default: $1000)")
    p_paper.add_argument("--days", type=int, default=30, help="Days to reach target (default: 30)")
    p_paper.add_argument("--symbol", type=str, help="Trade single pair (e.g. BTC/USDT)")
    p_paper.add_argument("--symbols", type=str, help="Preset or list: all, crypto, top10, stocks, metals, or BTC/USDT,ETH/USDT")
    p_paper.add_argument("--timeframe", type=str, help="Candle timeframe (e.g. 15m, 1h)")
    p_paper.add_argument("--risk", type=float, help="Risk per trade in %% of equity")
    p_paper.add_argument("--leverage", type=float, help="Max leverage cap")
    p_paper.add_argument("--once", action="store_true", help="Run one cycle then exit")
    p_paper.add_argument("--status", action="store_true", help="Show dashboard and exit")
    p_paper.add_argument("--reset", action="store_true", help="Reset paper wallet to starting balance")
    p_paper.add_argument("--state-file", type=str, default=None, help="Path to state file (default: paper_state.json)")

    # ── trade subcommand (live / dry-run) ────────────────────────────────
    p_trade = subparsers.add_parser("trade", help="Live or dry-run trading")
    p_trade.add_argument("--live", action="store_true", help="Place real orders (default: dry run)")
    p_trade.add_argument("--once", action="store_true", help="Run one cycle then exit")
    p_trade.add_argument("--symbol", type=str, help="Trade single pair (e.g. BTC/USDT)")
    p_trade.add_argument("--symbols", type=str, help="Preset or list: all, crypto, top10, stocks, metals")
    p_trade.add_argument("--timeframe", type=str, help="Candle timeframe (e.g. 15m, 1h)")
    p_trade.add_argument("--risk", type=float, help="Risk per trade in %% of equity")
    p_trade.add_argument("--leverage", type=float, help="Max leverage cap")

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(name)-8s  %(levelname)-5s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    cfg = Config.from_env(args.env)

    if args.command == "paper":
        cmd_paper(args, cfg)
    elif args.command == "trade":
        cmd_trade(args, cfg)
    else:
        parser.print_help()
        presets_list = ", ".join(PRESETS.keys())
        print("\nExamples:")
        print("  python main.py paper                        # Scan all (crypto+stocks+metals)")
        print("  python main.py paper --symbols crypto       # Top 100 crypto only")
        print("  python main.py paper --symbols top10        # Top 10 crypto only")
        print("  python main.py paper --symbols stocks       # Stocks only")
        print("  python main.py paper --symbols metals       # Gold & Silver")
        print("  python main.py paper --symbols top10,metals # Mix presets")
        print("  python main.py paper --symbol BTC/USDT      # Single pair")
        print("  python main.py paper --status               # Check progress")
        print("  python main.py paper --reset                # Reset wallet")
        print("  python main.py trade --once                 # Dry-run single cycle")
        print(f"\nPresets: {presets_list}")


if __name__ == "__main__":
    main()
