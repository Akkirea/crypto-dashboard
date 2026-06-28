from __future__ import annotations

from typing import Any, Optional

from app.analytics.utils import now_ms
from app.services.market_state import MarketState


def compute_cross_exchange(state: MarketState, stale_ms: int = 10_000) -> list[dict[str, Any]]:
    current_time = now_ms()
    rows: list[dict[str, Any]] = []

    for symbol in state.symbols:
        exchanges = sorted(
            set(state.exchange_latest_prices.keys()) | set(state.exchange_books.keys())
        )
        venues: list[dict[str, Any]] = []
        latest_trade_times: list[tuple[str, int]] = []

        for exchange in exchanges:
            price = state.exchange_latest_prices.get(exchange, {}).get(symbol)
            book = state.exchange_books.get(exchange, {}).get(symbol)
            trades = list(state.exchange_trades.get(exchange, {}).get(symbol, []))
            last_trade_time = trades[0].trade_time if trades else None
            last_seen = max(
                [value for value in [book.received_at if book else None, last_trade_time] if value]
                or [0]
            )
            if last_trade_time is not None:
                latest_trade_times.append((exchange, last_trade_time))

            venues.append(
                {
                    "exchange": exchange,
                    "symbol": symbol,
                    "latest_price": price,
                    "bid_price": book.bid_price if book else None,
                    "ask_price": book.ask_price if book else None,
                    "spread_bps": book.spread_bps if book else None,
                    "last_trade_time": last_trade_time,
                    "last_seen_at": last_seen or None,
                    "stale": not last_seen or current_time - last_seen > stale_ms,
                }
            )

        live_prices = [
            venue["latest_price"]
            for venue in venues
            if venue["latest_price"] is not None and not venue["stale"]
        ]
        min_price = min(live_prices) if live_prices else None
        max_price = max(live_prices) if live_prices else None
        mid = ((min_price + max_price) / 2) if min_price is not None and max_price is not None else None
        dispersion_bps = (
            ((max_price - min_price) / mid) * 10_000
            if min_price is not None and max_price is not None and mid
            else None
        )
        tightest = _tightest_venue(venues)
        leader = _price_discovery_leader(latest_trade_times, current_time, stale_ms)

        rows.append(
            {
                "symbol": symbol,
                "venues": venues,
                "price_dispersion_bps": dispersion_bps,
                "tightest_exchange": tightest,
                "price_discovery_leader": leader,
            }
        )

    return rows


def _tightest_venue(venues: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    candidates = [
        venue
        for venue in venues
        if venue.get("spread_bps") is not None and not venue.get("stale")
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda venue: venue["spread_bps"])


def _price_discovery_leader(
    latest_trade_times: list[tuple[str, int]], current_time: int, stale_ms: int
) -> Optional[dict[str, Any]]:
    live = [
        (exchange, event_time)
        for exchange, event_time in latest_trade_times
        if current_time - event_time <= stale_ms
    ]
    if not live:
        return None
    exchange, event_time = max(live, key=lambda item: item[1])
    peers = [peer_time for peer_exchange, peer_time in live if peer_exchange != exchange]
    lead_ms = event_time - max(peers) if peers else 0
    return {
        "exchange": exchange,
        "last_trade_time": event_time,
        "lead_ms": lead_ms,
        "method": "latest_trade_timestamp",
    }
