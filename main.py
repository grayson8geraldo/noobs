#!/usr/bin/env python3
"""
Crypto Futures Trader — small deposit accelerator.

Strategy:
  1. Round-number support/resistance levels
  2. Candlestick trend analysis (bull vs bear dominance)
  3. Risk-managed position sizing

Usage:
  python main.py                  # dry-run with .env config
  python main.py --live           # live trading (real orders)
  python main.py --symbol ETH/USDT --timeframe 1h
"""

from __future__ import annotations

import argparse
import logging
import sys

from trader.config import Config
from trader.exchange import create_exchange
from trader.engine import run_loop, run_once


def main() -> None:
    parser = argparse.ArgumentParser(description="Crypto Futures Trader")
    parser.add_argument("--live", action="store_true", help="Place real orders (default: dry run)")
    parser.add_argument("--once", action="store_true", help="Run one cycle then exit")
    parser.add_argument("--symbol", type=str, help="Trading pair (e.g. BTC/USDT)")
    parser.add_argument("--timeframe", type=str, help="Candle timeframe (e.g. 15m, 1h)")
    parser.add_argument("--risk", type=float, help="Risk per trade in %% of equity")
    parser.add_argument("--leverage", type=float, help="Max leverage cap")
    parser.add_argument("--env", type=str, default=".env", help="Path to .env file")
    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(name)-8s  %(levelname)-5s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    log = logging.getLogger("main")

    # Load config
    cfg = Config.from_env(args.env)
    if args.symbol:
        cfg.symbol = args.symbol
    if args.timeframe:
        cfg.timeframe = args.timeframe
    if args.risk:
        cfg.risk_pct = args.risk
    if args.leverage:
        cfg.max_leverage = args.leverage
    cfg.dry_run = not args.live

    log.info("=== Crypto Futures Trader ===")
    log.info("Exchange : %s", cfg.exchange_id)
    log.info("Symbol   : %s", cfg.symbol)
    log.info("Timeframe: %s", cfg.timeframe)
    log.info("Risk     : %.1f%%", cfg.risk_pct)
    log.info("Leverage : max %.0fx", cfg.max_leverage)
    log.info("Mode     : %s", "LIVE" if not cfg.dry_run else "DRY RUN")

    if cfg.dry_run and (not cfg.api_key or not cfg.api_secret):
        log.warning("No API keys found — running in dry-run mode with demo data.")

    # Connect to exchange
    exchange = create_exchange(cfg.exchange_id, cfg.api_key, cfg.api_secret)

    if args.once:
        results = run_once(
            exchange, cfg.symbol, cfg.timeframe,
            cfg.risk_pct, cfg.max_leverage, cfg.dry_run,
        )
        if not results:
            log.info("No signals generated.")
        for r in results:
            if r.error:
                log.error("Trade error: %s", r.error)
    else:
        run_loop(
            exchange, cfg.symbol, cfg.timeframe,
            cfg.risk_pct, cfg.max_leverage, cfg.dry_run,
        )


if __name__ == "__main__":
    main()
