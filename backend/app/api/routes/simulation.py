from __future__ import annotations

from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field

from app.config import settings
from app.simulation.backtest import BacktestConfig, run_sma_cross_backtest

router = APIRouter(prefix="/api/simulation", tags=["simulation"])


def _validate_symbol(symbol: str) -> str:
    normalized = symbol.upper()
    if normalized not in settings.symbol_list:
        raise HTTPException(status_code=404, detail=f"unsupported symbol: {symbol}")
    return normalized


class SimulatedMarketOrderRequest(BaseModel):
    portfolio_id: str = Field(default="default", max_length=64)
    symbol: str = Field(..., max_length=32)
    side: str = Field(..., pattern="^(buy|sell)$")
    quantity: Decimal = Field(..., gt=0)


class BacktestRequest(BaseModel):
    symbol: str = Field(..., max_length=32)
    interval: str = Field(default="1m", pattern="^(1m|5m)$")
    strategy: str = Field(default="sma_cross", pattern="^sma_cross$")
    initial_cash: Decimal = Field(default=Decimal("10000"), gt=0)
    short_window: int = Field(default=5, ge=2, le=200)
    long_window: int = Field(default=20, ge=3, le=500)
    limit: int = Field(default=500, ge=50, le=2000)


@router.get("/config")
async def simulation_config() -> dict[str, object]:
    return {
        "mode": "read_only_simulation_foundation",
        "read_only": True,
        "live_trading_enabled": False,
        "order_execution_enabled": False,
        "simulated_execution_enabled": True,
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
        "backtesting": {
            "enabled": True,
            "strategies": ["sma_cross"],
            "data_source": "postgres_closed_candles",
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


@router.get("/backtests/strategies")
async def backtest_strategies() -> dict[str, object]:
    return {
        "read_only": True,
        "strategies": [
            {
                "name": "sma_cross",
                "label": "SMA Crossover",
                "description": "Long-only candle backtest that buys when the short SMA crosses above the long SMA and exits on the reverse cross.",
                "parameters": {
                    "short_window": {"default": 5, "min": 2, "max": 200},
                    "long_window": {"default": 20, "min": 3, "max": 500},
                    "limit": {"default": 500, "min": 50, "max": 2000},
                },
            }
        ],
    }


@router.post("/backtests")
async def run_backtest(request: Request, payload: BacktestRequest) -> dict[str, object]:
    symbol = _validate_symbol(payload.symbol)
    if payload.short_window >= payload.long_window:
        raise HTTPException(status_code=422, detail="short_window must be lower than long_window")
    candles = await request.app.state.db.fetch_backtest_candles(
        symbol,
        payload.interval,
        exchange=settings.simulation_default_exchange,
        limit=payload.limit,
    )
    if len(candles) < payload.long_window:
        raise HTTPException(
            status_code=409,
            detail=f"not enough closed candles for backtest: have {len(candles)}, need {payload.long_window}",
        )

    result = run_sma_cross_backtest(
        candles,
        BacktestConfig(
            symbol=symbol,
            interval=payload.interval,
            initial_cash=payload.initial_cash,
            short_window=payload.short_window,
            long_window=payload.long_window,
            fee_bps=Decimal(str(settings.simulation_fee_bps)),
            slippage_bps=Decimal(str(settings.simulation_slippage_bps)),
        ),
    )
    return jsonable_encoder(result)


@router.get("/portfolio")
async def portfolio(
    request: Request,
    portfolio_id: str = Query("default", max_length=64),
) -> dict[str, object]:
    return await request.app.state.db.fetch_simulation_portfolio(
        portfolio_id=portfolio_id,
        marks=request.app.state.market_state.latest_prices,
    )


@router.get("/orders")
async def orders(
    request: Request,
    portfolio_id: str = Query("default", max_length=64),
    limit: int = Query(100, ge=1, le=500),
) -> list[dict[str, object]]:
    return await request.app.state.db.fetch_simulation_orders(
        portfolio_id=portfolio_id,
        limit=limit,
    )


@router.get("/fills")
async def fills(
    request: Request,
    portfolio_id: str = Query("default", max_length=64),
    limit: int = Query(100, ge=1, le=500),
) -> list[dict[str, object]]:
    return await request.app.state.db.fetch_simulation_fills(
        portfolio_id=portfolio_id,
        limit=limit,
    )


@router.get("/positions")
async def positions(
    request: Request,
    portfolio_id: str = Query("default", max_length=64),
) -> list[dict[str, object]]:
    return await request.app.state.db.fetch_simulation_positions(portfolio_id=portfolio_id)


@router.post("/orders")
async def submit_order(
    request: Request,
    order: SimulatedMarketOrderRequest,
) -> dict[str, object]:
    symbol = _validate_symbol(order.symbol)
    exchange = settings.simulation_default_exchange.lower()
    book = request.app.state.market_state.books.get(symbol)
    if book is None:
        persisted_book = await request.app.state.db.fetch_latest_book_top(symbol, exchange=exchange)
        if persisted_book is None:
            raise HTTPException(status_code=409, detail="no book available for simulated fill")
        bid_price = Decimal(str(persisted_book["bid_price"]))
        ask_price = Decimal(str(persisted_book["ask_price"]))
    else:
        bid_price = Decimal(str(book.bid_price))
        ask_price = Decimal(str(book.ask_price))

    result = await request.app.state.db.create_simulation_market_order(
        portfolio_id=order.portfolio_id,
        exchange=exchange,
        symbol=symbol,
        side=order.side,
        quantity=order.quantity,
        bid_price=bid_price,
        ask_price=ask_price,
        payload={
            "fill_model": {
                "price_source": settings.simulation_fill_price_source,
                "fee_bps": settings.simulation_fee_bps,
                "slippage_bps": settings.simulation_slippage_bps,
                "latency_ms": settings.simulation_latency_ms,
            }
        },
    )
    return result


@router.post("/portfolio/reset")
async def reset_portfolio(
    request: Request,
    portfolio_id: str = Query("default", max_length=64),
) -> dict[str, object]:
    await request.app.state.db.reset_simulation_portfolio(portfolio_id=portfolio_id)
    return await request.app.state.db.fetch_simulation_portfolio(
        portfolio_id=portfolio_id,
        marks=request.app.state.market_state.latest_prices,
    )
