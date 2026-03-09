"""
Predefined symbol lists — top crypto, stocks, and precious metals.

All symbols use the Bybit/Binance futures naming convention (SYMBOL/USDT).
For stocks and metals — these are available as tokenized perpetuals on
exchanges like Bybit or as CFDs.
"""

# ── Top 100 Crypto by market cap ─────────────────────────────────────────
CRYPTO_TOP_100 = [
    "BTC/USDT",
    "ETH/USDT",
    "BNB/USDT",
    "SOL/USDT",
    "XRP/USDT",
    "ADA/USDT",
    "DOGE/USDT",
    "AVAX/USDT",
    "DOT/USDT",
    "LINK/USDT",
    "TRX/USDT",
    "MATIC/USDT",
    "SHIB/USDT",
    "LTC/USDT",
    "BCH/USDT",
    "NEAR/USDT",
    "UNI/USDT",
    "APT/USDT",
    "ICP/USDT",
    "FIL/USDT",
    "ETC/USDT",
    "ATOM/USDT",
    "ARB/USDT",
    "OP/USDT",
    "IMX/USDT",
    "STX/USDT",
    "HBAR/USDT",
    "INJ/USDT",
    "VET/USDT",
    "MKR/USDT",
    "GRT/USDT",
    "RUNE/USDT",
    "THETA/USDT",
    "FTM/USDT",
    "ALGO/USDT",
    "SEI/USDT",
    "SUI/USDT",
    "AAVE/USDT",
    "FLOW/USDT",
    "SNX/USDT",
    "AXS/USDT",
    "SAND/USDT",
    "MANA/USDT",
    "EGLD/USDT",
    "XTZ/USDT",
    "EOS/USDT",
    "KAVA/USDT",
    "IOTA/USDT",
    "NEO/USDT",
    "ZIL/USDT",
    "CRV/USDT",
    "LDO/USDT",
    "1INCH/USDT",
    "ENS/USDT",
    "COMP/USDT",
    "DYDX/USDT",
    "GMX/USDT",
    "BLUR/USDT",
    "CFX/USDT",
    "GALA/USDT",
    "APE/USDT",
    "PEPE/USDT",
    "WLD/USDT",
    "ORDI/USDT",
    "TIA/USDT",
    "JTO/USDT",
    "PYTH/USDT",
    "JUP/USDT",
    "WIF/USDT",
    "BONK/USDT",
    "FLOKI/USDT",
    "PENDLE/USDT",
    "W/USDT",
    "ENA/USDT",
    "STRK/USDT",
    "PIXEL/USDT",
    "MANTA/USDT",
    "DYM/USDT",
    "ONDO/USDT",
    "AR/USDT",
    "FET/USDT",
    "RNDR/USDT",
    "TAO/USDT",
    "KAS/USDT",
    "TON/USDT",
    "NOT/USDT",
    "PEOPLE/USDT",
    "BOME/USDT",
    "ZRO/USDT",
    "IO/USDT",
    "BRETT/USDT",
    "MEW/USDT",
    "RENDER/USDT",
    "JASMY/USDT",
    "CHZ/USDT",
    "XLM/USDT",
    "QNT/USDT",
    "ROSE/USDT",
    "ZEC/USDT",
    "DASH/USDT",
]

# ── Top Stocks (tokenized perpetuals / CFDs) ─────────────────────────────
# Available on Bybit and some other exchanges as perpetual contracts
STOCKS = [
    "AAPL/USDT",
    "MSFT/USDT",
    "GOOGL/USDT",
    "AMZN/USDT",
    "NVDA/USDT",
    "TSLA/USDT",
    "META/USDT",
    "AMD/USDT",
    "NFLX/USDT",
    "COIN/USDT",
    "MSTR/USDT",
    "GME/USDT",
    "AMC/USDT",
    "SPY/USDT",
    "QQQ/USDT",
]

# ── Precious Metals ──────────────────────────────────────────────────────
METALS = [
    "XAUUSDT",    # Gold
    "XAGUSDT",    # Silver
]

# ── Combined preset lists ────────────────────────────────────────────────
PRESETS = {
    "crypto":     CRYPTO_TOP_100,
    "stocks":     STOCKS,
    "metals":     METALS,
    "all":        CRYPTO_TOP_100 + STOCKS + METALS,
    "top10":      CRYPTO_TOP_100[:10],
    "top20":      CRYPTO_TOP_100[:20],
    "top50":      CRYPTO_TOP_100[:50],
}


def resolve_symbols(spec: str) -> list[str]:
    """Resolve a symbol spec into a list of symbols.

    The spec can be:
    - A preset name: "crypto", "stocks", "metals", "all", "top10", etc.
    - A comma-separated list: "BTC/USDT,ETH/USDT,SOL/USDT"
    - A combination: "top10,stocks,metals" or "crypto,XAUUSDT"
    """
    parts = [p.strip() for p in spec.split(",") if p.strip()]
    result: list[str] = []
    seen: set[str] = set()

    for part in parts:
        if part.lower() in PRESETS:
            for s in PRESETS[part.lower()]:
                if s not in seen:
                    result.append(s)
                    seen.add(s)
        else:
            # Treat as individual symbol
            sym = part.upper()
            if "/" not in sym and not sym.endswith("USDT"):
                sym = sym + "/USDT"
            if sym not in seen:
                result.append(sym)
                seen.add(sym)

    return result
