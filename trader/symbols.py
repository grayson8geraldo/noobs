"""
Predefined symbol lists — top crypto and precious metals.

All symbols use the Bybit futures naming convention (SYMBOL/USDT).
"""

# ── Top Crypto by market cap (verified on Bybit futures) ─────────────────
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
    "GRT/USDT",
    "RUNE/USDT",
    "THETA/USDT",
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
    "KAVA/USDT",
    "ZIL/USDT",
    "CRV/USDT",
    "LDO/USDT",
    "1INCH/USDT",
    "ENS/USDT",
    "COMP/USDT",
    "DYDX/USDT",
    "GMX/USDT",
    "BLUR/USDT",
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
    "MANTA/USDT",
    "DYM/USDT",
    "ONDO/USDT",
    "AR/USDT",
    "FET/USDT",
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
    "POL/USDT",     # ex-MATIC
    "S/USDT",       # ex-FTM (Sonic)
    "TAO/USDT",
    "EOS/USDT",
    "NEO/USDT",
    "ZEC/USDT",
    "DASH/USDT",
    "CFX/USDT",
    "IOTA/USDT",
    "MKR/USDT",
    "PIXEL/USDT",
]

# ── Precious Metals ──────────────────────────────────────────────────────
METALS = [
    "XAUUSDT",    # Gold
    "XAGUSDT",    # Silver
]

# ── Combined preset lists ────────────────────────────────────────────────
PRESETS = {
    "crypto":     CRYPTO_TOP_100,
    "metals":     METALS,
    "all":        CRYPTO_TOP_100 + METALS,
    "top10":      CRYPTO_TOP_100[:10],
    "top20":      CRYPTO_TOP_100[:20],
    "top50":      CRYPTO_TOP_100[:50],
}


def filter_available(symbols: list[str], exchange) -> list[str]:
    """Keep only symbols that actually exist on the exchange.

    Logs removed symbols once so the user knows what was dropped.
    """
    import logging
    log = logging.getLogger("trader")
    available = []
    removed = []
    for s in symbols:
        if s in exchange.markets:
            available.append(s)
        else:
            removed.append(s)
    if removed:
        log.warning("Dropped %d symbols not on exchange: %s", len(removed), ", ".join(removed))
    return available


def resolve_symbols(spec: str) -> list[str]:
    """Resolve a symbol spec into a list of symbols.

    The spec can be:
    - A preset name: "crypto", "metals", "all", "top10", etc.
    - A comma-separated list: "BTC/USDT,ETH/USDT,SOL/USDT"
    - A combination: "top10,metals" or "crypto,XAUUSDT"
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
