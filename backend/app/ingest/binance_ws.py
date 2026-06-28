from __future__ import annotations

import asyncio
import json
import logging
import random
from collections.abc import Awaitable, Callable
from typing import Union

import websockets

from app.config import settings
from app.ingest.normalizers import normalize
from app.schemas.market import BookTopEvent, CandleEvent, OrderBookDepthEvent, TradeEvent
from app.services.market_state import MarketState

logger = logging.getLogger(__name__)

MarketEvent = Union[TradeEvent, BookTopEvent, CandleEvent, OrderBookDepthEvent]
EventHandler = Callable[[MarketEvent], Awaitable[None]]


class BinanceMarketDataClient:
    def __init__(self, state: MarketState, on_event: EventHandler) -> None:
        self.state = state
        self.on_event = on_event
        self._stop = asyncio.Event()

    def stream_url(self) -> str:
        streams: list[str] = []
        for symbol in settings.symbol_list:
            lower = symbol.lower()
            streams.append(f"{lower}@trade")
            streams.append(f"{lower}@bookTicker")
            streams.append(f"{lower}@depth20@100ms")
            for interval in settings.interval_list:
                streams.append(f"{lower}@kline_{interval}")
        return f"{settings.binance_ws_base}?streams={'/'.join(streams)}"

    async def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                await self._connect_once()
                backoff = 1.0
            except asyncio.CancelledError:
                raise
            except Exception:
                self.state.mark_connected(False)
                logger.exception("binance websocket disconnected")

            delay = min(30.0, backoff) * random.uniform(0.8, 1.2)
            await asyncio.sleep(delay)
            backoff = min(30.0, backoff * 2)

    async def _connect_once(self) -> None:
        url = self.stream_url()
        logger.info("connecting to binance public websocket")
        async with websockets.connect(url, ping_interval=20, ping_timeout=20) as websocket:
            self.state.mark_connected(True)
            logger.info("binance websocket connected")
            async for raw in websocket:
                message = json.loads(raw)
                stream = message.get("stream", "").lower()
                payload = message.get("data", {})
                event = normalize(stream, payload)
                if event:
                    await self.on_event(event)
