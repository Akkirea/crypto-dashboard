from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SymbolMapping:
    canonical: str
    base: str
    quote: str
    venues: dict[str, str]


def _split_binance_symbol(symbol: str) -> tuple[str, str]:
    for quote in ("USDT", "USD", "USDC", "BTC", "ETH"):
        if symbol.endswith(quote):
            return symbol[: -len(quote)], quote
    return symbol[:-3], symbol[-3:]


def build_symbol_mappings(symbols: list[str]) -> dict[str, SymbolMapping]:
    mappings: dict[str, SymbolMapping] = {}
    for symbol in symbols:
        base, quote = _split_binance_symbol(symbol)
        usd_quote = "USD" if quote == "USDT" else quote
        mappings[symbol] = SymbolMapping(
            canonical=symbol,
            base=base,
            quote=quote,
            venues={
                "binance": symbol,
                "coinbase": f"{base}-{usd_quote}",
                "kraken": f"{base}/{usd_quote}",
                "bybit": symbol,
            },
        )
    return mappings


def venue_symbol_to_canonical(exchange: str, venue_symbol: str, symbols: list[str]) -> Optional[str]:
    for canonical, mapping in build_symbol_mappings(symbols).items():
        if mapping.venues.get(exchange) == venue_symbol:
            return canonical
    return None


def venue_symbols(exchange: str, symbols: list[str]) -> list[str]:
    return [
        mapping.venues[exchange]
        for mapping in build_symbol_mappings(symbols).values()
        if exchange in mapping.venues
    ]
