from __future__ import annotations

from typing import Any

from app.analytics.utils import WINDOWS_MS, annualized_realized_vol, now_ms, regime_from_vol
from app.services.market_state import MarketState


def compute_volatility(state: MarketState, window: str = "5m") -> list[dict[str, Any]]:
    current_time = now_ms()
    window_ms = WINDOWS_MS.get(window, WINDOWS_MS["5m"])
    cutoff = current_time - window_ms
    rows: list[dict[str, Any]] = []

    for symbol in state.symbols:
        trades = [trade for trade in state.trades.get(symbol, []) if trade.trade_time >= cutoff]
        prices = [trade.price for trade in trades]
        realized_vol = annualized_realized_vol(prices, window_ms)

        candles = [
            candle
            for candle in state.candle_history.get(symbol, {}).get("1m", [])
            if candle.open_time >= cutoff
        ]
        ranges = [
            ((candle.high - candle.low) / candle.open) * 100
            for candle in candles
            if candle.open > 0
        ]
        avg_candle_range = sum(ranges) / len(ranges) if ranges else None

        rows.append(
            {
                "symbol": symbol,
                "window": window,
                "realized_volatility_pct": realized_vol,
                "average_candle_range_pct": avg_candle_range,
                "regime": regime_from_vol(realized_vol),
                "sample_count": len(prices),
            }
        )

    ranked = sorted(
        rows,
        key=lambda item: item["realized_volatility_pct"]
        if item["realized_volatility_pct"] is not None
        else -1,
        reverse=True,
    )
    for index, row in enumerate(ranked, start=1):
        row["volatility_rank"] = index
    return ranked
