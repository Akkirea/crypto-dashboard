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
from app.schemas.market import (
    BookLevel,
    BookTopEvent,
    CandleEvent,
    OrderBookDepthEvent,
    TradeEvent,
)
from app.services.market_state import MarketState

logger = logging.getLogger(__name__)

MarketEvent = Union[TradeEvent, BookTopEvent, CandleEvent, OrderBookDepthEvent]
EventHandler = Callable[[MarketEvent], Awaitable[None]]


class KrakenMarketDataClient:
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
                logger.exception("kraken websocket disconnected")

            delay = min(30.0, backoff) * random.uniform(0.8, 1.2)
            await asyncio.sleep(delay)
            backoff = min(30.0, backoff * 2)

    async def _connect_once(self) -> None:
        symbols = venue_symbols("kraken", settings.symbol_list)
        subscriptions = [
            {"method": "subscribe", "params": {"channel": "ticker", "symbol": symbols}},
            {"method": "subscribe", "params": {"channel": "trade", "symbol": symbols}},
            {
                "method": "subscribe",
                "params": {"channel": "book", "symbol": symbols, "depth": 25},
            },
        ]
        logger.info("connecting to kraken public websocket")
        async with websockets.connect(settings.kraken_ws_url, ping_interval=20, ping_timeout=20) as ws:
            for subscription in subscriptions:
                await ws.send(json.dumps(subscription))
            logger.info("kraken websocket connected")
            async for raw in ws:
                payload = json.loads(raw)
                for event in self._normalize(payload):
                    await self.on_event(event)

    def _normalize(self, payload: dict[str, Any]) -> list[MarketEvent]:
        channel = payload.get("channel")
        if not channel or "data" not in payload:
            return []

        events: list[MarketEvent] = []
        for item in payload.get("data") or []:
            symbol = item.get("symbol")
            canonical = venue_symbol_to_canonical("kraken", symbol, settings.symbol_list)
            if not canonical:
                continue
            received_at = int(time.time() * 1000)
            event_time = _parse_kraken_time_ms(item.get("timestamp")) or received_at

            if channel == "ticker":
                events.extend(_ticker_events(canonical, item, received_at, event_time))
            elif channel == "trade":
                event = _trade_event(canonical, item, received_at, event_time)
                if event:
                    events.append(event)
            elif channel == "book":
                event = _book_event(canonical, item, received_at, event_time)
                if event:
                    events.append(event)
        return events


def _ticker_events(
    canonical: str, item: dict[str, Any], received_at: int, event_time: int
) -> list[MarketEvent]:
    bid = _float_or_none(item.get("bid"))
    ask = _float_or_none(item.get("ask"))
    last = _float_or_none(item.get("last"))
    events: list[MarketEvent] = []
    if bid is not None and ask is not None and bid > 0 and ask > 0:
        mid = (bid + ask) / 2
        spread = max(0.0, ask - bid)
        events.append(
            BookTopEvent(
                exchange="kraken",
                symbol=canonical,
                bid_price=bid,
                bid_quantity=_float_or_none(item.get("bid_qty")) or 0.0,
                ask_price=ask,
                ask_quantity=_float_or_none(item.get("ask_qty")) or 0.0,
                spread=spread,
                spread_bps=(spread / mid) * 10_000 if mid else None,
                event_time=event_time,
                received_at=received_at,
                ingest_latency_ms=max(0, received_at - event_time),
            )
        )
    if last is not None:
        events.append(
            TradeEvent(
                exchange="kraken",
                symbol=canonical,
                trade_id=received_at,
                price=last,
                quantity=0.0,
                buyer_maker=False,
                event_time=event_time,
                trade_time=event_time,
                received_at=received_at,
                ingest_latency_ms=max(0, received_at - event_time),
            )
        )
    return events


def _trade_event(
    canonical: str, item: dict[str, Any], received_at: int, event_time: int
) -> Optional[TradeEvent]:
    price = _float_or_none(item.get("price"))
    qty = _float_or_none(item.get("qty"))
    if price is None:
        return None
    return TradeEvent(
        exchange="kraken",
        symbol=canonical,
        trade_id=int(item.get("trade_id") or received_at),
        price=price,
        quantity=qty or 0.0,
        buyer_maker=item.get("side") == "sell",
        event_time=event_time,
        trade_time=event_time,
        received_at=received_at,
        ingest_latency_ms=max(0, received_at - event_time),
    )


def _book_event(
    canonical: str, item: dict[str, Any], received_at: int, event_time: int
) -> Optional[OrderBookDepthEvent]:
    bids = _levels(item.get("bids") or item.get("bid"))
    asks = _levels(item.get("asks") or item.get("ask"))
    if not bids or not asks:
        return None
    return OrderBookDepthEvent(
        exchange="kraken",
        symbol=canonical,
        bids=bids,
        asks=asks,
        event_time=event_time,
        received_at=received_at,
        update_id=item.get("checksum"),
        ingest_latency_ms=max(0, received_at - event_time),
    )


def _levels(raw: Any) -> list[BookLevel]:
    levels: list[BookLevel] = []
    for level in raw or []:
        if isinstance(level, dict):
            price = _float_or_none(level.get("price"))
            qty = _float_or_none(level.get("qty"))
        elif isinstance(level, list) and len(level) >= 2:
            price = _float_or_none(level[0])
            qty = _float_or_none(level[1])
        else:
            continue
        if price is not None and qty is not None:
            levels.append(BookLevel(price=price, quantity=qty))
    return levels


def _float_or_none(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_kraken_time_ms(value: Any) -> Optional[int]:
    if not value:
        return None
    try:
        from datetime import datetime

        if isinstance(value, (int, float)):
            return int(float(value) * 1000)
        return int(datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp() * 1000)
    except (TypeError, ValueError):
        return None
