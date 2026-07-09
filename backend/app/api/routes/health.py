from fastapi import APIRouter, HTTPException, Request

from app.config import settings

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "crypto-market-dashboard-backend",
        "mode": "read_only",
    }


@router.get("/health/ready")
async def ready(request: Request) -> dict[str, object]:
    db = request.app.state.db
    db_ready = await db.ping()
    market_health = request.app.state.market_state.health().model_dump()
    is_ready = db_ready and market_health["connected"]
    if not is_ready:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "not_ready",
                "database": "connected" if db_ready else "unavailable",
                "market_data": market_health,
                "mode": "read_only",
            },
        )
    return {
        "status": "ready",
        "database": "connected",
        "market_data": market_health,
        "mode": "read_only",
    }


@router.get("/health/market-data")
async def market_data_health(request: Request) -> dict[str, object]:
    return request.app.state.market_state.health().model_dump()


@router.get("/health/database")
async def database_health(request: Request) -> dict[str, object]:
    db = request.app.state.db
    connected = await db.ping()
    return {
        "status": "ok" if connected else "unavailable",
        "connected": connected,
        "database_size_bytes": await db.database_size_bytes() if connected else None,
        "max_database_bytes": settings.max_database_bytes,
        "retention": {
            "enabled": settings.retention_enabled,
            "interval_seconds": settings.retention_interval_seconds,
            "delete_limit": settings.retention_delete_limit,
            "persist_raw_trades": settings.persist_raw_trades,
            "persist_order_book_top": settings.persist_order_book_top,
            "order_book_persist_interval_ms": settings.order_book_persist_interval_ms,
            "rollups": {
                "enabled": settings.rollups_enabled,
                "interval_seconds": settings.rollup_interval_seconds,
                "lookback_hours": settings.rollup_lookback_hours,
                "order_book_bucket_minutes": settings.order_book_rollup_bucket_minutes,
            },
            "tables": {
                "trades": f"{settings.trades_retention_days}d",
                "order_book_top": f"{settings.order_book_retention_hours}h",
                "candles": f"{settings.candles_retention_days}d",
                "analytics_events": f"{settings.analytics_events_retention_days}d",
                "analytics_snapshots": f"{settings.analytics_snapshots_retention_days}d",
                "system_events": f"{settings.system_events_retention_days}d",
            },
        },
        "tables": await db.table_stats() if connected else [],
    }
