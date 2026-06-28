from __future__ import annotations

from statistics import mean
from typing import Any, Optional

from app.services.market_state import MarketState


BPS_BUCKETS = [10, 25, 50]


def compute_liquidity(state: MarketState, exchange: str = "binance") -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for symbol in state.symbols:
        depth = state.exchange_depth.get(exchange, {}).get(symbol)
        if not depth or not depth.bids or not depth.asks:
            rows.append(_empty_row(exchange, symbol))
            continue

        best_bid = depth.bids[0].price
        best_ask = depth.asks[0].price
        mid = (best_bid + best_ask) / 2 if best_bid and best_ask else None
        bid_notional_top = sum(level.price * level.quantity for level in depth.bids)
        ask_notional_top = sum(level.price * level.quantity for level in depth.asks)
        total_top = bid_notional_top + ask_notional_top
        imbalance = (
            (bid_notional_top - ask_notional_top) / total_top
            if total_top > 0
            else None
        )
        depth_buckets = {
            f"{bucket}bps": _depth_within_bps(depth.bids, depth.asks, mid, bucket)
            for bucket in BPS_BUCKETS
        }
        collapse = _collapse_metrics(state, exchange, symbol, depth_buckets["25bps"]["total_notional"])

        rows.append(
            {
                "exchange": exchange,
                "symbol": symbol,
                "best_bid": best_bid,
                "best_ask": best_ask,
                "mid_price": mid,
                "top_bid_notional": bid_notional_top,
                "top_ask_notional": ask_notional_top,
                "order_book_imbalance": imbalance,
                "depth": depth_buckets,
                "collapse": collapse,
                "sample_count": len(state.exchange_depth_history.get(exchange, {}).get(symbol, [])),
                "last_update_at": depth.received_at,
            }
        )

    return sorted(
        rows,
        key=lambda row: row.get("collapse", {}).get("drop_pct")
        if row.get("collapse", {}).get("drop_pct") is not None
        else -999,
        reverse=True,
    )


def _empty_row(exchange: str, symbol: str) -> dict[str, Any]:
    return {
        "exchange": exchange,
        "symbol": symbol,
        "best_bid": None,
        "best_ask": None,
        "mid_price": None,
        "top_bid_notional": None,
        "top_ask_notional": None,
        "order_book_imbalance": None,
        "depth": {},
        "collapse": {"drop_pct": None, "baseline_notional": None, "current_notional": None},
        "sample_count": 0,
        "last_update_at": None,
    }


def _depth_within_bps(bids: list[Any], asks: list[Any], mid: Optional[float], bps: int) -> dict[str, float]:
    if not mid:
        return {"bid_notional": 0.0, "ask_notional": 0.0, "total_notional": 0.0}
    bid_floor = mid * (1 - bps / 10_000)
    ask_ceiling = mid * (1 + bps / 10_000)
    bid_notional = sum(level.price * level.quantity for level in bids if level.price >= bid_floor)
    ask_notional = sum(level.price * level.quantity for level in asks if level.price <= ask_ceiling)
    return {
        "bid_notional": bid_notional,
        "ask_notional": ask_notional,
        "total_notional": bid_notional + ask_notional,
    }


def _collapse_metrics(
    state: MarketState, exchange: str, symbol: str, current_notional: float
) -> dict[str, Optional[float]]:
    history = list(state.exchange_depth_history.get(exchange, {}).get(symbol, []))[1:61]
    totals: list[float] = []
    for depth in history:
        if not depth.bids or not depth.asks:
            continue
        mid = (depth.bids[0].price + depth.asks[0].price) / 2
        totals.append(_depth_within_bps(depth.bids, depth.asks, mid, 25)["total_notional"])

    baseline = mean(totals) if totals else None
    drop_pct = (
        ((baseline - current_notional) / baseline) * 100
        if baseline and baseline > 0
        else None
    )
    return {
        "drop_pct": drop_pct,
        "baseline_notional": baseline,
        "current_notional": current_notional,
    }
