from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.analytics import router as analytics_router
from app.api.routes.health import router as health_router
from app.api.routes.market import router as market_router
from app.analytics.worker import AnalyticsWorker
from app.config import settings
from app.db.pool import Database
from app.ingest.binance_ws import BinanceMarketDataClient, MarketEvent
from app.ingest.bybit_ws import BybitMarketDataClient
from app.ingest.coinbase_ws import CoinbaseMarketDataClient
from app.ingest.kraken_ws import KrakenMarketDataClient
from app.logging import configure_logging
from app.services.broadcaster import Broadcaster
from app.services.market_state import MarketState

configure_logging()
logger = logging.getLogger(__name__)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    state = MarketState(settings.symbol_list)
    broadcaster = Broadcaster()
    db = Database()
    await db.connect()
    await db.record_system_event(
        "api",
        "startup",
        status="ok",
        message="backend startup completed",
        payload={"mode": "read_only"},
    )

    async def handle_event(event: MarketEvent) -> None:
        state.apply(event)
        await db.save_event(event)
        if event.exchange == "binance" and event.type != "order_book_depth":
            await broadcaster.broadcast(event.model_dump())

    client = BinanceMarketDataClient(state, handle_event)
    coinbase_client = CoinbaseMarketDataClient(state, handle_event) if settings.enable_coinbase else None
    kraken_client = KrakenMarketDataClient(state, handle_event) if settings.enable_kraken else None
    bybit_client = BybitMarketDataClient(state, handle_event) if settings.enable_bybit else None
    analytics_worker = AnalyticsWorker(state, db)
    ingest_task = asyncio.create_task(client.run())
    coinbase_task = (
        asyncio.create_task(coinbase_client.run()) if coinbase_client is not None else None
    )
    kraken_task = asyncio.create_task(kraken_client.run()) if kraken_client is not None else None
    bybit_task = asyncio.create_task(bybit_client.run()) if bybit_client is not None else None
    health_task = asyncio.create_task(_publish_health(state, broadcaster))
    analytics_task = asyncio.create_task(analytics_worker.run())
    db_reconnect_task = asyncio.create_task(_run_database_reconnect(db))
    retention_task = asyncio.create_task(_run_retention(db))
    rollup_task = asyncio.create_task(_run_rollups(db))

    app.state.market_state = state
    app.state.broadcaster = broadcaster
    app.state.db = db
    app.state.ingest_client = client
    app.state.coinbase_ingest_client = coinbase_client
    app.state.kraken_ingest_client = kraken_client
    app.state.bybit_ingest_client = bybit_client
    app.state.analytics_worker = analytics_worker

    try:
        yield
    finally:
        logger.info("shutting down")
        await db.record_system_event(
            "api",
            "shutdown",
            status="stopping",
            message="backend shutdown requested",
        )
        await client.stop()
        if coinbase_client is not None:
            await coinbase_client.stop()
        if kraken_client is not None:
            await kraken_client.stop()
        if bybit_client is not None:
            await bybit_client.stop()
        await analytics_worker.stop()
        ingest_task.cancel()
        if coinbase_task is not None:
            coinbase_task.cancel()
        if kraken_task is not None:
            kraken_task.cancel()
        if bybit_task is not None:
            bybit_task.cancel()
        health_task.cancel()
        analytics_task.cancel()
        db_reconnect_task.cancel()
        retention_task.cancel()
        rollup_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await ingest_task
        if coinbase_task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await coinbase_task
        if kraken_task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await kraken_task
        if bybit_task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await bybit_task
        with contextlib.suppress(asyncio.CancelledError):
            await health_task
        with contextlib.suppress(asyncio.CancelledError):
            await analytics_task
        with contextlib.suppress(asyncio.CancelledError):
            await db_reconnect_task
        with contextlib.suppress(asyncio.CancelledError):
            await retention_task
        with contextlib.suppress(asyncio.CancelledError):
            await rollup_task
        await db.close()


async def _publish_health(state: MarketState, broadcaster: Broadcaster) -> None:
    while True:
        state.client_count = len(broadcaster.clients)
        await broadcaster.broadcast(state.health().model_dump())
        await asyncio.sleep(1)


async def _run_retention(db: Database) -> None:
    await asyncio.sleep(settings.retention_initial_delay_seconds)
    while True:
        try:
            deleted = await db.apply_retention()
            if deleted:
                logger.info("retention cleanup completed", extra={"deleted": deleted})
                await db.record_system_event(
                    "retention",
                    "cleanup_completed",
                    status="ok",
                    message="retention cleanup completed",
                    payload={"deleted": deleted},
                )
            await asyncio.sleep(settings.retention_interval_seconds)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("retention cleanup failed")
            await db.record_system_event(
                "retention",
                "cleanup_failed",
                severity="error",
                status="failed",
                message=str(exc),
            )


async def _run_database_reconnect(db: Database) -> None:
    was_connected = db.pool is not None
    while True:
        try:
            if db.pool is None:
                await db.connect()
                if db.pool is not None and not was_connected:
                    was_connected = True
                    await db.record_system_event(
                        "database",
                        "reconnected",
                        status="ok",
                        message="database persistence connected",
                    )
            elif not await db.ping():
                was_connected = False
                logger.warning("database ping failed; reconnect will be retried")
            await asyncio.sleep(settings.database_reconnect_interval_seconds)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("database reconnect loop failed")
            was_connected = False
            await asyncio.sleep(settings.database_reconnect_interval_seconds)


async def _run_rollups(db: Database) -> None:
    await asyncio.sleep(settings.rollup_initial_delay_seconds)
    while True:
        try:
            refreshed = await db.refresh_order_book_rollups()
            if refreshed:
                logger.info("order book rollups refreshed", extra={"refreshed": refreshed})
                await db.record_system_event(
                    "rollups",
                    "refresh_completed",
                    status="ok",
                    message="order book rollups refreshed",
                    payload={"refreshed": refreshed},
                )
            await asyncio.sleep(settings.rollup_interval_seconds)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("order book rollup refresh failed")
            await db.record_system_event(
                "rollups",
                "refresh_failed",
                severity="error",
                status="failed",
                message=str(exc),
            )


app = FastAPI(title="Crypto Market Dashboard Backend", lifespan=lifespan)
cors_origins = settings.cors_origin_list
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials="*" not in cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health_router)
app.include_router(market_router)
app.include_router(analytics_router)
