from __future__ import annotations

from typing import Any

from app.analytics.utils import WINDOWS_MS, now_ms, safe_mean, safe_pstdev
from app.services.market_state import MarketState


def compute_spreads(state: MarketState, window: str = "5m") -> list[dict[str, Any]]:
    current_time = now_ms()
    window_ms = WINDOWS_MS.get(window, WINDOWS_MS["5m"])
    cutoff = current_time - window_ms
    rows: list[dict[str, Any]] = []

    for symbol in state.symbols:
        history = [
            book
            for book in state.book_history.get(symbol, [])
            if book.received_at >= cutoff and book.spread_bps is not None
        ]
        spreads = [float(book.spread_bps) for book in history if book.spread_bps is not None]
        latest = state.books.get(symbol)
        avg_spread = safe_mean(spreads)
        spread_volatility = safe_pstdev(spreads)
        latest_spread = latest.spread_bps if latest else None
        widening_ratio = (
            latest_spread / avg_spread
            if latest_spread is not None and avg_spread not in (None, 0)
            else None
        )

        rows.append(
            {
                "symbol": symbol,
                "exchange": "binance",
                "latest_spread_bps": latest_spread,
                "average_spread_bps": avg_spread,
                "spread_volatility_bps": spread_volatility,
                "widening_ratio": widening_ratio,
                "sample_count": len(spreads),
            }
        )

    ranked = sorted(
        rows,
        key=lambda item: item["average_spread_bps"]
        if item["average_spread_bps"] is not None
        else float("inf"),
    )
    for index, row in enumerate(ranked, start=1):
        row["tightness_rank"] = index
    return ranked
