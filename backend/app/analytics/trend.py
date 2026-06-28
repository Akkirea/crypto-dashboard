from __future__ import annotations

from typing import Any, Optional

from app.analytics.utils import WINDOWS_MS, now_ms, pct_change
from app.services.market_state import MarketState


def _reference_price(trades: list[Any], cutoff_ms: int) -> Optional[float]:
    older = [trade for trade in trades if trade.trade_time <= cutoff_ms]
    if older:
        return older[0].price
    if trades:
        return trades[-1].price
    return None


def _volume_since(trades: list[Any], cutoff_ms: int) -> float:
    return sum(trade.quantity for trade in trades if trade.trade_time >= cutoff_ms)


def compute_trends(state: MarketState) -> list[dict[str, Any]]:
    current_time = now_ms()
    rows: list[dict[str, Any]] = []

    for symbol in state.symbols:
        trades = list(state.trades.get(symbol, []))
        latest_price = state.latest_prices.get(symbol)
        windows: dict[str, dict[str, Any]] = {}
        score_parts: list[float] = []

        for label, window_ms in WINDOWS_MS.items():
            cutoff = current_time - window_ms
            baseline = _reference_price(trades, cutoff)
            price_change = pct_change(latest_price, baseline)
            recent_volume = _volume_since(trades, cutoff)
            prior_volume = _volume_since(trades, cutoff - window_ms) - recent_volume
            volume_change = pct_change(recent_volume, prior_volume) if prior_volume > 0 else None

            if price_change is not None:
                score_parts.append(price_change)
            if volume_change is not None:
                score_parts.append(min(100.0, max(-100.0, volume_change)) * 0.1)

            windows[label] = {
                "price_change_pct": price_change,
                "volume": recent_volume,
                "volume_change_pct": volume_change,
                "sample_count": len([trade for trade in trades if trade.trade_time >= cutoff]),
            }

        momentum_score = sum(score_parts) / len(score_parts) if score_parts else 0.0
        rows.append(
            {
                "symbol": symbol,
                "latest_price": latest_price,
                "momentum_score": momentum_score,
                "windows": windows,
            }
        )

    ranked = sorted(rows, key=lambda item: item["momentum_score"], reverse=True)
    for index, row in enumerate(ranked, start=1):
        row["rank"] = index
    return ranked
