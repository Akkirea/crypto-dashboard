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
        await db.close()


async def _publish_health(state: MarketState, broadcaster: Broadcaster) -> None:
    while True:
        state.client_count = len(broadcaster.clients)
        await broadcaster.broadcast(state.health().model_dump())
        await asyncio.sleep(1)


app = FastAPI(title="Crypto Market Dashboard Backend", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health_router)
app.include_router(market_router)
app.include_router(analytics_router)
