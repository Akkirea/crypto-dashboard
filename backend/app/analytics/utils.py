from __future__ import annotations

import math
import time
from statistics import mean, pstdev
from typing import Iterable, Optional, Sequence


WINDOWS_MS = {
    "1m": 60_000,
    "5m": 5 * 60_000,
    "15m": 15 * 60_000,
    "1h": 60 * 60_000,
}


def now_ms() -> int:
    return int(time.time() * 1000)


def pct_change(current: Optional[float], previous: Optional[float]) -> Optional[float]:
    if current is None or previous is None or previous == 0:
        return None
    return ((current - previous) / previous) * 100


def bps_change(current: Optional[float], previous: Optional[float]) -> Optional[float]:
    change = pct_change(current, previous)
    if change is None:
        return None
    return change * 100


def safe_mean(values: Iterable[float]) -> Optional[float]:
    collected = list(values)
    if not collected:
        return None
    return mean(collected)


def safe_pstdev(values: Sequence[float]) -> Optional[float]:
    if len(values) < 2:
        return None
    return pstdev(values)


def annualized_realized_vol(prices: Sequence[float], elapsed_ms: int) -> Optional[float]:
    if len(prices) < 3 or elapsed_ms <= 0:
        return None
    returns: list[float] = []
    ordered = list(reversed(prices))
    for left, right in zip(ordered, ordered[1:]):
        if left > 0 and right > 0:
            returns.append(math.log(right / left))
    if len(returns) < 2:
        return None
    observations_per_year = (365 * 24 * 60 * 60 * 1000) / max(1, elapsed_ms / len(returns))
    return pstdev(returns) * math.sqrt(observations_per_year) * 100


def regime_from_vol(volatility_pct: Optional[float]) -> str:
    if volatility_pct is None:
        return "insufficient_data"
    if volatility_pct < 35:
        return "quiet"
    if volatility_pct < 80:
        return "normal"
    if volatility_pct < 150:
        return "elevated"
    return "extreme"
