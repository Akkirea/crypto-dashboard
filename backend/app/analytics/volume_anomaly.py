from __future__ import annotations

from statistics import mean, pstdev
from typing import Any, Optional

from app.analytics.utils import now_ms
from app.services.market_state import MarketState


def compute_volume_anomalies(
    state: MarketState,
    exchange: str = "binance",
    bucket_ms: int = 60_000,
    baseline_buckets: int = 5,
) -> list[dict[str, Any]]:
    current_time = now_ms()
    current_start = current_time - bucket_ms
    baseline_start = current_start - bucket_ms * baseline_buckets
    rows: list[dict[str, Any]] = []

    for symbol in state.symbols:
        trades = [
            trade
            for trade in state.exchange_trades.get(exchange, {}).get(symbol, [])
            if trade.trade_time >= baseline_start
        ]
        current_volume = sum(trade.quantity for trade in trades if trade.trade_time >= current_start)
        buckets = []
        for index in range(baseline_buckets):
            bucket_start = baseline_start + index * bucket_ms
            bucket_end = bucket_start + bucket_ms
            buckets.append(
                sum(
                    trade.quantity
                    for trade in trades
                    if bucket_start <= trade.trade_time < bucket_end
                )
            )

        baseline_mean = mean(buckets) if buckets else 0.0
        baseline_std = pstdev(buckets) if len(buckets) > 1 else 0.0
        z_score = _zscore(current_volume, baseline_mean, baseline_std)
        ratio = (current_volume / baseline_mean) if baseline_mean > 0 else None

        rows.append(
            {
                "exchange": exchange,
                "symbol": symbol,
                "window": "1m",
                "current_volume": current_volume,
                "baseline_mean": baseline_mean,
                "baseline_std": baseline_std,
                "z_score": z_score,
                "volume_ratio": ratio,
                "sample_count": len(trades),
            }
        )

    return sorted(
        rows,
        key=lambda item: item["z_score"] if item["z_score"] is not None else -999,
        reverse=True,
    )


def _zscore(value: float, baseline_mean: float, baseline_std: float) -> Optional[float]:
    if baseline_std > 0:
        return (value - baseline_mean) / baseline_std
    if baseline_mean == 0 and value > 0:
        return None
    if baseline_mean > 0:
        return (value - baseline_mean) / baseline_mean
    return None
