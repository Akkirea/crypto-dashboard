from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query, Request

from app.analytics.cross_exchange import compute_cross_exchange
from app.analytics.liquidity import compute_liquidity
from app.analytics.scoring import analytics_summary
from app.analytics.spreads import compute_spreads
from app.analytics.trend import compute_trends
from app.analytics.volume_anomaly import compute_volume_anomalies
from app.analytics.volatility import compute_volatility

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/summary")
async def summary(request: Request) -> dict[str, object]:
    worker = getattr(request.app.state, "analytics_worker", None)
    if worker and worker.latest_summary:
        return worker.latest_summary
    return analytics_summary(request.app.state.market_state)


@router.get("/trends")
async def trends(request: Request) -> list[dict[str, object]]:
    return compute_trends(request.app.state.market_state)


@router.get("/spreads")
async def spreads(
    request: Request,
    window: str = Query("5m", pattern="^(1m|5m|15m|1h)$"),
) -> list[dict[str, object]]:
    return compute_spreads(request.app.state.market_state, window=window)


@router.get("/volatility")
async def volatility(
    request: Request,
    window: str = Query("5m", pattern="^(1m|5m|15m|1h)$"),
) -> list[dict[str, object]]:
    return compute_volatility(request.app.state.market_state, window=window)


@router.get("/cross-exchange")
async def cross_exchange(request: Request) -> list[dict[str, object]]:
    return compute_cross_exchange(request.app.state.market_state)


@router.get("/volume-anomalies")
async def volume_anomalies(request: Request) -> list[dict[str, object]]:
    return compute_volume_anomalies(request.app.state.market_state)


@router.get("/liquidity")
async def liquidity(request: Request) -> list[dict[str, object]]:
    return compute_liquidity(request.app.state.market_state)


@router.get("/events")
async def events(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
) -> list[dict[str, object]]:
    db_events = await request.app.state.db.fetch_analytics_events(limit=limit)
    if db_events:
        return db_events
    worker = getattr(request.app.state, "analytics_worker", None)
    if not worker:
        return []
    return list(worker.recent_events)[:limit]


@router.get("/snapshots/latest")
async def latest_snapshot(
    request: Request,
    metric_family: str = Query("summary", pattern="^[a-z_]+$"),
) -> Optional[dict[str, object]]:
    snapshot = await request.app.state.db.fetch_latest_analytics_snapshot(metric_family)
    if snapshot:
        return snapshot
    worker = getattr(request.app.state, "analytics_worker", None)
    if worker and worker.latest_summary and metric_family == "summary":
        return {
            "metric_family": "summary",
            "exchange": "binance",
            "window": None,
            "payload": worker.latest_summary,
            "computed_at": worker.latest_summary.get("computed_at"),
        }
    return None


@router.get("/history")
async def history(
    request: Request,
    metric_family: str = Query("summary", pattern="^[a-z_]+$"),
    window: Optional[str] = Query(None, max_length=32),
    limit: int = Query(200, ge=1, le=1000),
) -> list[dict[str, object]]:
    rows = await request.app.state.db.fetch_analytics_history(
        metric_family=metric_family,
        window=window,
        limit=limit,
    )
    if rows:
        return rows

    worker = getattr(request.app.state, "analytics_worker", None)
    if worker and worker.latest_summary and metric_family == "summary":
        return [
            {
                "metric_family": "summary",
                "exchange": "binance",
                "window": None,
                "payload": worker.latest_summary,
                "computed_at": worker.latest_summary.get("computed_at"),
            }
        ]
    return []


@router.get("/history/events")
async def event_history(
    request: Request,
    limit: int = Query(200, ge=1, le=1000),
) -> list[dict[str, object]]:
    return await request.app.state.db.fetch_analytics_events(limit=limit)
