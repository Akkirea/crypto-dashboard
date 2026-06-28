from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from collections.abc import Awaitable, Callable
from typing import Any, Optional, Union

import websockets

from app.config import settings
from app.ingest.symbols import venue_symbol_to_canonical, venue_symbols
from app.schemas.market import BookTopEvent, CandleEvent, OrderBookDepthEvent, TradeEvent
from app.services.market_state import MarketState

logger = logging.getLogger(__name__)

MarketEvent = Union[TradeEvent, BookTopEvent, CandleEvent, OrderBookDepthEvent]
EventHandler = Callable[[MarketEvent], Awaitable[None]]


class CoinbaseMarketDataClient:
    def __init__(self, state: MarketState, on_event: EventHandler) -> None:
        self.state = state
        self.on_event = on_event
        self._stop = asyncio.Event()

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
                logger.exception("coinbase websocket disconnected")

            delay = min(30.0, backoff) * random.uniform(0.8, 1.2)
            await asyncio.sleep(delay)
            backoff = min(30.0, backoff * 2)

    async def _connect_once(self) -> None:
        product_ids = venue_symbols("coinbase", settings.symbol_list)
        subscribe = {
            "type": "subscribe",
            "product_ids": product_ids,
            "channels": ["ticker"],
        }
        logger.info("connecting to coinbase public websocket")
        async with websockets.connect(settings.coinbase_ws_url, ping_interval=20, ping_timeout=20) as ws:
            await ws.send(json.dumps(subscribe))
            logger.info("coinbase websocket connected")
            async for raw in ws:
                payload = json.loads(raw)
                events = self._normalize(payload)
                for event in events:
                    await self.on_event(event)

    def _normalize(self, payload: dict[str, Any]) -> list[MarketEvent]:
        if payload.get("type") != "ticker":
            return []

        product_id = payload.get("product_id")
        canonical = venue_symbol_to_canonical("coinbase", product_id, settings.symbol_list)
        if not canonical:
            return []

        received_at = int(time.time() * 1000)
        event_time = _parse_coinbase_time_ms(payload.get("time")) or received_at
        price = _float_or_none(payload.get("price"))
        size = _float_or_none(payload.get("last_size")) or 0.0
        trade_id = int(payload.get("trade_id") or received_at)
        side = payload.get("side")
        bid = _float_or_none(payload.get("best_bid"))
        ask = _float_or_none(payload.get("best_ask"))
        events: list[MarketEvent] = []

        if bid is not None and ask is not None and bid > 0 and ask > 0:
            mid = (bid + ask) / 2
            spread = max(0.0, ask - bid)
            events.append(
                BookTopEvent(
                    exchange="coinbase",
                    symbol=canonical,
                    bid_price=bid,
                    bid_quantity=0.0,
                    ask_price=ask,
                    ask_quantity=0.0,
                    spread=spread,
                    spread_bps=(spread / mid) * 10_000 if mid else None,
                    event_time=event_time,
                    received_at=received_at,
                    ingest_latency_ms=max(0, received_at - event_time),
                )
            )

        if price is None:
            return events

        events.append(
            TradeEvent(
                exchange="coinbase",
                symbol=canonical,
                trade_id=trade_id,
                price=price,
                quantity=size,
                buyer_maker=side == "sell",
                event_time=event_time,
                trade_time=event_time,
                received_at=received_at,
                ingest_latency_ms=max(0, received_at - event_time),
            )
        )
        return events


def _float_or_none(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_coinbase_time_ms(value: Any) -> Optional[int]:
    if not value:
        return None
    try:
        from datetime import datetime

        return int(datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp() * 1000)
    except ValueError:
        return None
