"""
Thin wrapper around ccxt for fetching OHLCV data and placing futures orders.

Supports a "public-only" mode (no API keys) for paper trading — only market
data endpoints are called, no authenticated requests.
"""

from __future__ import annotations

import ccxt
import pandas as pd


def create_exchange(
    exchange_id: str,
    api_key: str = "",
    api_secret: str = "",
    public_only: bool = False,
) -> ccxt.Exchange:
    """Instantiate a ccxt exchange with futures enabled.

    Parameters
    ----------
    public_only : bool
        If True, skip API keys and only use public endpoints (market data).
        Useful for paper trading.
    """
    cls = getattr(ccxt, exchange_id)
    config: dict = {
        "options": {"defaultType": "future"},
        "enableRateLimit": True,
    }
    if not public_only and api_key and api_secret:
        config["apiKey"] = api_key
        config["secret"] = api_secret

    exchange: ccxt.Exchange = cls(config)
    exchange.load_markets()
    return exchange


def fetch_ohlcv(
    exchange: ccxt.Exchange,
    symbol: str,
    timeframe: str = "15m",
    limit: int = 100,
) -> pd.DataFrame:
    """Fetch OHLCV candles and return a pandas DataFrame."""
    raw = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df


def fetch_price(exchange: ccxt.Exchange, symbol: str) -> float:
    """Fetch latest ticker price (public endpoint, no auth needed)."""
    ticker = exchange.fetch_ticker(symbol)
    return float(ticker["last"])


def set_leverage(exchange: ccxt.Exchange, symbol: str, leverage: int) -> None:
    exchange.set_leverage(leverage, symbol)


def place_market_order(
    exchange: ccxt.Exchange,
    symbol: str,
    side: str,
    quantity: float,
    stop_loss: float | None = None,
    take_profit: float | None = None,
) -> dict:
    """Place a market order with optional SL/TP."""
    params: dict = {}
    if stop_loss is not None:
        params["stopLoss"] = {"triggerPrice": stop_loss, "type": "market"}
    if take_profit is not None:
        params["takeProfit"] = {"triggerPrice": take_profit, "type": "market"}

    order = exchange.create_order(
        symbol=symbol,
        type="market",
        side=side,
        amount=quantity,
        params=params,
    )
    return order


def get_balance(exchange: ccxt.Exchange, coin: str = "USDT") -> float:
    balance = exchange.fetch_balance()
    return float(balance.get("free", {}).get(coin, 0))
