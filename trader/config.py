"""
Configuration loader — reads .env + CLI args.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv


@dataclass
class Config:
    exchange_id: str = "bybit"
    api_key: str = ""
    api_secret: str = ""
    symbol: str = "BTC/USDT"
    timeframe: str = "15m"
    deposit: float = 150.0
    risk_pct: float = 2.0
    max_leverage: float = 10.0
    dry_run: bool = True

    @classmethod
    def from_env(cls, env_path: str = ".env") -> "Config":
        load_dotenv(env_path)
        return cls(
            exchange_id=os.getenv("EXCHANGE_ID", "bybit"),
            api_key=os.getenv("EXCHANGE_API_KEY", ""),
            api_secret=os.getenv("EXCHANGE_API_SECRET", ""),
            symbol=os.getenv("SYMBOL", "BTC/USDT"),
            timeframe=os.getenv("TIMEFRAME", "15m"),
            deposit=float(os.getenv("DEPOSIT", "150")),
            risk_pct=float(os.getenv("RISK_PER_TRADE_PCT", "2")),
            max_leverage=float(os.getenv("MAX_LEVERAGE", "10")),
        )
