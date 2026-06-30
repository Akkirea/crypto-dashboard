from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from app.config import settings

router = APIRouter(prefix="/api/simulation", tags=["simulation"])


def _validate_symbol(symbol: str) -> str:
    normalized = symbol.upper()
    if normalized not in settings.symbol_list:
        raise HTTPException(status_code=404, detail=f"unsupported symbol: {symbol}")
    return normalized


@router.get("/config")
async def simulation_config() -> dict[str, object]:
    return {
        "mode": "read_only_simulation_foundation",
        "read_only": True,
        "live_trading_enabled": False,
        "order_execution_enabled": False,
        "symbols": settings.symbol_list,
        "intervals": settings.interval_list,
        "default_exchange": settings.simulation_default_exchange,
        "fill_model": {
            "price_source": settings.simulation_fill_price_source,
            "fee_bps": settings.simulation_fee_bps,
            "slippage_bps": settings.simulation_slippage_bps,
            "latency_ms": settings.simulation_latency_ms,
        },
        "data_sources": {
            "live_snapshot": "in_memory_market_state",
            "trades": "postgres_trades",
            "candles": "postgres_candles",
            "book_top": "postgres_order_book_top",
        },
    }


@router.get("/market/snapshot")
async def market_snapshot(request: Request) -> dict[str, object]:
    state = request.app.state.market_state
    return {
        "type": "simulation_market_snapshot",
        "read_only": True,
        "health": state.health().model_dump(),
        "symbols": state.symbols,
        "prices": state.latest_prices,
        "books": {symbol: book.model_dump() for symbol, book in state.books.items()},
    }


@router.get("/market/trades")
async def recent_trades(
    request: Request,
    symbol: str = Query(..., max_length=32),
    exchange: Optional[str] = Query(None, max_length=32),
    limit: int = Query(200, ge=1, le=1000),
) -> list[dict[str, object]]:
    return await request.app.state.db.fetch_recent_trades(
        _validate_symbol(symbol),
        exchange=(exchange or settings.simulation_default_exchange).lower(),
        limit=limit,
    )


@router.get("/market/candles")
async def recent_candles(
    request: Request,
    symbol: str = Query(..., max_length=32),
    interval: str = Query("1m", pattern="^(1m|5m)$"),
    exchange: Optional[str] = Query(None, max_length=32),
    limit: int = Query(200, ge=1, le=1000),
) -> list[dict[str, object]]:
    return await request.app.state.db.fetch_recent_candles(
        _validate_symbol(symbol),
        interval,
        exchange=(exchange or settings.simulation_default_exchange).lower(),
        limit=limit,
    )


@router.get("/market/book")
async def latest_book(
    request: Request,
    symbol: str = Query(..., max_length=32),
    exchange: Optional[str] = Query(None, max_length=32),
) -> Optional[dict[str, object]]:
    return await request.app.state.db.fetch_latest_book_top(
        _validate_symbol(symbol),
        exchange=(exchange or settings.simulation_default_exchange).lower(),
    )
