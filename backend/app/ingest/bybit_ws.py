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


class BybitMarketDataClient:
    def __init__(self, state: MarketState, on_event: EventHandler) -> None:
        self.state = state
        self.on_event = on_event
        self._stop = asyncio.Event()
        self._books: dict[str, dict[str, dict[float, float]]] = {}

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
                logger.exception("bybit websocket disconnected")

            delay = min(30.0, backoff) * random.uniform(0.8, 1.2)
            await asyncio.sleep(delay)
            backoff = min(30.0, backoff * 2)

    async def _connect_once(self) -> None:
        symbols = venue_symbols("bybit", settings.symbol_list)
        args: list[str] = []
        for symbol in symbols:
            args.append(f"tickers.{symbol}")
            args.append(f"publicTrade.{symbol}")
            args.append(f"orderbook.50.{symbol}")

        logger.info("connecting to bybit public websocket")
        async with websockets.connect(settings.bybit_spot_ws_url, ping_interval=20, ping_timeout=20) as ws:
            await ws.send(json.dumps({"op": "subscribe", "args": args}))
            logger.info("bybit websocket connected")
            async for raw in ws:
                payload = json.loads(raw)
                for event in self._normalize(payload):
                    await self.on_event(event)

    def _normalize(self, payload: dict[str, Any]) -> list[MarketEvent]:
        topic = payload.get("topic", "")
        data = payload.get("data")
        received_at = int(time.time() * 1000)
        event_time = int(payload.get("ts") or received_at)

        if topic.startswith("tickers."):
            symbol = topic.split(".", 1)[1]
            return self._ticker_events(symbol, data or {}, received_at, event_time)
        if topic.startswith("publicTrade."):
            symbol = topic.split(".", 1)[1]
            return self._trade_events(symbol, data or [], received_at)
        if topic.startswith("orderbook."):
            parts = topic.split(".")
            symbol = parts[-1]
            event = self._orderbook_event(symbol, payload, received_at, event_time)
            return [event] if event else []
        return []

    def _ticker_events(
        self, venue_symbol: str, item: dict[str, Any], received_at: int, event_time: int
    ) -> list[MarketEvent]:
        canonical = venue_symbol_to_canonical("bybit", venue_symbol, settings.symbol_list)
        if not canonical:
            return []
        bid = _float_or_none(item.get("bid1Price"))
        ask = _float_or_none(item.get("ask1Price"))
        last = _float_or_none(item.get("lastPrice"))
        events: list[MarketEvent] = []
        if bid is not None and ask is not None and bid > 0 and ask > 0:
            mid = (bid + ask) / 2
            spread = max(0.0, ask - bid)
            events.append(
                BookTopEvent(
                    exchange="bybit",
                    symbol=canonical,
                    bid_price=bid,
                    bid_quantity=_float_or_none(item.get("bid1Size")) or 0.0,
                    ask_price=ask,
                    ask_quantity=_float_or_none(item.get("ask1Size")) or 0.0,
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
                    exchange="bybit",
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

    def _trade_events(
        self, venue_symbol: str, items: list[dict[str, Any]], received_at: int
    ) -> list[MarketEvent]:
        canonical = venue_symbol_to_canonical("bybit", venue_symbol, settings.symbol_list)
        if not canonical:
            return []
        events: list[MarketEvent] = []
        for item in items:
            price = _float_or_none(item.get("p"))
            qty = _float_or_none(item.get("v"))
            event_time = int(item.get("T") or received_at)
            if price is None:
                continue
            events.append(
                TradeEvent(
                    exchange="bybit",
                    symbol=canonical,
                    trade_id=int(item.get("i") or event_time),
                    price=price,
                    quantity=qty or 0.0,
                    buyer_maker=item.get("S") == "Sell",
                    event_time=event_time,
                    trade_time=event_time,
                    received_at=received_at,
                    ingest_latency_ms=max(0, received_at - event_time),
                )
            )
        return events

    def _orderbook_event(
        self, venue_symbol: str, payload: dict[str, Any], received_at: int, event_time: int
    ) -> Optional[OrderBookDepthEvent]:
        canonical = venue_symbol_to_canonical("bybit", venue_symbol, settings.symbol_list)
        if not canonical:
            return None
        data = payload.get("data") or {}
        book = self._books.setdefault(venue_symbol, {"bids": {}, "asks": {}})
        if payload.get("type") == "snapshot":
            book["bids"] = _level_map(data.get("b"))
            book["asks"] = _level_map(data.get("a"))
        else:
            _apply_delta(book["bids"], data.get("b"))
            _apply_delta(book["asks"], data.get("a"))

        bids = [
            BookLevel(price=price, quantity=qty)
            for price, qty in sorted(book["bids"].items(), reverse=True)[:50]
            if qty > 0
        ]
        asks = [
            BookLevel(price=price, quantity=qty)
            for price, qty in sorted(book["asks"].items())[:50]
            if qty > 0
        ]
        if not bids or not asks:
            return None
        return OrderBookDepthEvent(
            exchange="bybit",
            symbol=canonical,
            bids=bids,
            asks=asks,
            event_time=event_time,
            received_at=received_at,
            update_id=data.get("u"),
            ingest_latency_ms=max(0, received_at - event_time),
        )


def _level_map(raw: Any) -> dict[float, float]:
    result: dict[float, float] = {}
    for level in raw or []:
        if len(level) < 2:
            continue
        price = _float_or_none(level[0])
        qty = _float_or_none(level[1])
        if price is not None and qty is not None and qty > 0:
            result[price] = qty
    return result


def _apply_delta(book_side: dict[float, float], raw: Any) -> None:
    for level in raw or []:
        if len(level) < 2:
            continue
        price = _float_or_none(level[0])
        qty = _float_or_none(level[1])
        if price is None or qty is None:
            continue
        if qty <= 0:
            book_side.pop(price, None)
        else:
            book_side[price] = qty


def _float_or_none(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
