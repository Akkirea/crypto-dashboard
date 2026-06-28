from __future__ import annotations

from typing import Any

from app.analytics.cross_exchange import compute_cross_exchange
from app.analytics.liquidity import compute_liquidity
from app.analytics.spreads import compute_spreads
from app.analytics.trend import compute_trends
from app.analytics.volume_anomaly import compute_volume_anomalies
from app.analytics.volatility import compute_volatility
from app.services.market_state import MarketState


def analytics_summary(state: MarketState) -> dict[str, Any]:
    trends = compute_trends(state)
    spreads = compute_spreads(state)
    volatility = compute_volatility(state)
    cross_exchange = compute_cross_exchange(state)
    volume_anomalies = compute_volume_anomalies(state)
    liquidity = compute_liquidity(state)

    return {
        "type": "analytics_summary",
        "trend_rankings": trends,
        "spread_rankings": spreads,
        "volatility_rankings": volatility,
        "cross_exchange": cross_exchange,
        "volume_anomalies": volume_anomalies,
        "liquidity": liquidity,
        "leaders": {
            "trend": trends[0] if trends else None,
            "tightest_spread": spreads[0] if spreads else None,
            "most_volatile": volatility[0] if volatility else None,
        },
    }
