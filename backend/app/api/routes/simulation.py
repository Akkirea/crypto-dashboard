from __future__ import annotations

from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field

from app.config import settings
from app.simulation.backtest import (
    BACKTEST_STRATEGIES,
    BacktestConfig,
    required_lookback,
    run_backtest as run_backtest_engine,
    strategy_definitions,
)
from app.simulation.automation import AutomationConfig

router = APIRouter(prefix="/api/simulation", tags=["simulation"])
INTERVAL_PATTERN = "^(1m|5m|15m|1h)$"


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
    interval: str = Field(default="5m", pattern=INTERVAL_PATTERN)
    strategy: str = Field(default="momentum_breakout", pattern="^(sma_cross|momentum_breakout)$")
    initial_cash: Decimal = Field(default=Decimal("10000"), gt=0)
    short_window: int = Field(default=5, ge=2, le=200)
    long_window: int = Field(default=20, ge=3, le=500)
    momentum_window: int = Field(default=20, ge=3, le=500)
    breakout_bps: Decimal = Field(default=Decimal("25"), ge=0, le=1000)
    exit_window: int = Field(default=10, ge=2, le=200)
    limit: int = Field(default=500, ge=50, le=2000)
    persist: bool = True


class AutomationRequest(BaseModel):
    portfolio_id: str = Field(default="default", max_length=64)
    symbol: str = Field(default="BTCUSDT", max_length=32)
    interval: str = Field(default="5m", pattern=INTERVAL_PATTERN)
    strategy: str = Field(default="momentum_breakout", pattern="^(sma_cross|momentum_breakout)$")
    poll_seconds: float = Field(default=settings.simulation_automation_poll_seconds, ge=5, le=3600)
    notional: Decimal = Field(
        default=Decimal(str(settings.simulation_automation_default_notional)),
        gt=0,
    )
    max_position_notional: Decimal = Field(
        default=Decimal(str(settings.simulation_automation_max_position_notional)),
        gt=0,
    )
    short_window: int = Field(default=5, ge=2, le=200)
    long_window: int = Field(default=20, ge=3, le=500)
    momentum_window: int = Field(default=20, ge=3, le=500)
    breakout_bps: Decimal = Field(default=Decimal("25"), ge=0, le=1000)
    exit_window: int = Field(default=10, ge=2, le=200)
    trend_window: int = Field(default=50, ge=5, le=1000)
    min_trend_bps: Decimal = Field(default=Decimal("0"), ge=-10000, le=10000)
    atr_window: int = Field(default=14, ge=2, le=500)
    atr_target_multiplier: Decimal = Field(default=Decimal("1.20"), ge=0, le=20)
    min_take_profit_bps: Decimal = Field(default=Decimal("50"), ge=0, le=10000)
    max_take_profit_bps: Decimal = Field(default=Decimal("150"), ge=0, le=10000)
    min_close_location: Decimal = Field(default=Decimal("0.65"), ge=0, le=1)
    min_atr_bps: Decimal = Field(default=Decimal("10"), ge=0, le=10000)
    min_expected_move_bps: Decimal = Field(default=Decimal("35"), ge=0, le=10000)
    min_volume_ratio: Decimal = Field(default=Decimal("1.20"), ge=0, le=100)
    stop_loss_bps: Decimal = Field(default=Decimal("50"), ge=1, le=5000)
    trailing_stop_bps: Decimal = Field(default=Decimal("35"), ge=1, le=5000)
    take_profit_bps: Decimal = Field(default=Decimal("75"), ge=0, le=10000)
    min_holding_minutes: Decimal = Field(default=Decimal("3"), ge=0, le=1440)
    max_holding_minutes: Decimal = Field(default=Decimal("90"), ge=1, le=10080)
    cooldown_minutes: Decimal = Field(default=Decimal("5"), ge=0, le=1440)
    max_spread_bps: Decimal = Field(default=Decimal("10"), ge=0, le=10000)
    daily_max_loss: Decimal = Field(default=Decimal("25"), ge=0, le=1000000)
    max_trades_per_day: int = Field(default=10, ge=1, le=10000)
    max_fee_burn_per_day: Decimal = Field(default=Decimal("5"), ge=0, le=1000000)
    pause_after_loss_streak: int = Field(default=3, ge=1, le=10000)
    profit_only_exits: bool = True


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
            "strategies": list(BACKTEST_STRATEGIES.keys()),
            "data_source": "postgres_closed_candles",
        },
        "automation": {
            "enabled": True,
            "default_notional": settings.simulation_automation_default_notional,
            "max_position_notional": settings.simulation_automation_max_position_notional,
            "poll_seconds": settings.simulation_automation_poll_seconds,
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
    interval: str = Query("1m", pattern=INTERVAL_PATTERN),
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


@router.get("/automation")
async def automation_status(request: Request) -> dict[str, object]:
    return jsonable_encoder(request.app.state.automation_worker.status())


@router.post("/automation/start")
async def start_automation(request: Request, payload: AutomationRequest) -> dict[str, object]:
    symbol = _validate_symbol(payload.symbol)
    try:
        status = await request.app.state.automation_worker.start_strategy(
            AutomationConfig(
                portfolio_id=payload.portfolio_id,
                exchange=settings.simulation_default_exchange,
                symbol=symbol,
                interval=payload.interval,
                strategy=payload.strategy,
                enabled=True,
                poll_seconds=payload.poll_seconds,
                notional=payload.notional,
                max_position_notional=payload.max_position_notional,
                short_window=payload.short_window,
                long_window=payload.long_window,
                momentum_window=payload.momentum_window,
                breakout_bps=payload.breakout_bps,
                exit_window=payload.exit_window,
                trend_window=payload.trend_window,
                min_trend_bps=payload.min_trend_bps,
                atr_window=payload.atr_window,
                atr_target_multiplier=payload.atr_target_multiplier,
                min_take_profit_bps=payload.min_take_profit_bps,
                max_take_profit_bps=payload.max_take_profit_bps,
                min_close_location=payload.min_close_location,
                min_atr_bps=payload.min_atr_bps,
                min_expected_move_bps=payload.min_expected_move_bps,
                min_volume_ratio=payload.min_volume_ratio,
                stop_loss_bps=payload.stop_loss_bps,
                trailing_stop_bps=payload.trailing_stop_bps,
                take_profit_bps=payload.take_profit_bps,
                min_holding_minutes=payload.min_holding_minutes,
                max_holding_minutes=payload.max_holding_minutes,
                cooldown_minutes=payload.cooldown_minutes,
                max_spread_bps=payload.max_spread_bps,
                daily_max_loss=payload.daily_max_loss,
                max_trades_per_day=payload.max_trades_per_day,
                max_fee_burn_per_day=payload.max_fee_burn_per_day,
                pause_after_loss_streak=payload.pause_after_loss_streak,
                profit_only_exits=payload.profit_only_exits,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return jsonable_encoder(status)


@router.post("/automation/stop")
async def stop_automation(request: Request) -> dict[str, object]:
    return jsonable_encoder(await request.app.state.automation_worker.stop_strategy())


@router.post("/automation/evaluate")
async def evaluate_automation(request: Request) -> dict[str, object]:
    signal = await request.app.state.automation_worker.evaluate_once()
    return jsonable_encoder(
        {
            "status": request.app.state.automation_worker.status(),
            "signal": signal,
        }
    )


@router.get("/automation/signals")
async def automation_signals(
    request: Request,
    portfolio_id: str = Query("default", max_length=64),
    limit: int = Query(50, ge=1, le=200),
) -> list[dict[str, object]]:
    return await request.app.state.db.fetch_strategy_signals(
        portfolio_id=portfolio_id,
        limit=limit,
    )


@router.get("/backtests/strategies")
async def backtest_strategies() -> dict[str, object]:
    return {
        "read_only": True,
        "strategies": strategy_definitions(),
    }


@router.get("/backtests/runs")
async def backtest_runs(
    request: Request,
    symbol: Optional[str] = Query(None, max_length=32),
    limit: int = Query(25, ge=1, le=100),
) -> list[dict[str, object]]:
    normalized_symbol = _validate_symbol(symbol) if symbol else None
    return await request.app.state.db.fetch_backtest_runs(
        symbol=normalized_symbol,
        limit=limit,
    )


@router.get("/backtests/runs/{run_id}")
async def backtest_run(request: Request, run_id: int) -> dict[str, object]:
    run = await request.app.state.db.fetch_backtest_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"backtest run not found: {run_id}")
    return jsonable_encoder(run)


@router.post("/backtests")
async def run_backtest(request: Request, payload: BacktestRequest) -> dict[str, object]:
    symbol = _validate_symbol(payload.symbol)
    if payload.strategy == "sma_cross" and payload.short_window >= payload.long_window:
        raise HTTPException(status_code=422, detail="short_window must be lower than long_window")
    config = BacktestConfig(
        symbol=symbol,
        interval=payload.interval,
        strategy=payload.strategy,
        initial_cash=payload.initial_cash,
        short_window=payload.short_window,
        long_window=payload.long_window,
        momentum_window=payload.momentum_window,
        breakout_bps=payload.breakout_bps,
        exit_window=payload.exit_window,
        fee_bps=Decimal(str(settings.simulation_fee_bps)),
        slippage_bps=Decimal(str(settings.simulation_slippage_bps)),
    )
    lookback = required_lookback(config)
    candles = await request.app.state.db.fetch_backtest_candles(
        symbol,
        payload.interval,
        exchange=settings.simulation_default_exchange,
        limit=payload.limit,
    )
    if len(candles) < lookback:
        raise HTTPException(
            status_code=409,
            detail=f"not enough closed candles for backtest: have {len(candles)}, need {lookback}",
        )

    try:
        result = run_backtest_engine(candles, config)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if payload.persist:
        saved = await request.app.state.db.save_backtest_run(
            result,
            exchange=settings.simulation_default_exchange,
        )
        if saved:
            result["run_id"] = saved["id"]
            result["created_at"] = saved["created_at"]
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


@router.get("/pnl")
async def pnl(
    request: Request,
    portfolio_id: str = Query("default", max_length=64),
    experiment_id: Optional[int] = Query(None, ge=1),
) -> dict[str, object]:
    return await request.app.state.db.fetch_simulation_pnl(
        portfolio_id=portfolio_id,
        marks=request.app.state.market_state.latest_prices,
        experiment_id=experiment_id,
    )


@router.get("/experiments")
async def experiments(
    request: Request,
    portfolio_id: str = Query("default", max_length=64),
    limit: int = Query(25, ge=1, le=100),
) -> list[dict[str, object]]:
    return await request.app.state.db.fetch_simulation_experiments(
        portfolio_id=portfolio_id,
        limit=limit,
    )


@router.get("/experiments/{experiment_id}/pnl")
async def experiment_pnl(
    request: Request,
    experiment_id: int,
    portfolio_id: str = Query("default", max_length=64),
) -> dict[str, object]:
    return await request.app.state.db.fetch_simulation_pnl(
        portfolio_id=portfolio_id,
        marks=request.app.state.market_state.latest_prices,
        experiment_id=experiment_id,
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
