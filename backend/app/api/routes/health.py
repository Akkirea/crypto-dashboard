from fastapi import APIRouter, Request

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
    return {
        "status": "ready",
        "database": "connected" if db.pool else "disabled",
        "mode": "read_only",
    }


@router.get("/health/market-data")
async def market_data_health(request: Request) -> dict[str, object]:
    return request.app.state.market_state.health().model_dump()
