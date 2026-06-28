from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Any, Optional, Union

from app.schemas.market import (
    BookTopEvent,
    CandleEvent,
    HealthEvent,
    OrderBookDepthEvent,
    TradeEvent,
)


class MarketState:
    def __init__(self, symbols: list[str]) -> None:
        self.symbols = symbols
        self.connected = False
        self.reconnect_count = 0
        self.last_message_at: Optional[int] = None
        self.last_latency_ms: Optional[int] = None
        self.message_counts: dict[str, int] = defaultdict(int)
        self.latest_prices: dict[str, float] = {}
        self.books: dict[str, BookTopEvent] = {}
        self.exchange_latest_prices: dict[str, dict[str, float]] = defaultdict(dict)
        self.exchange_books: dict[str, dict[str, BookTopEvent]] = defaultdict(dict)
        self.exchange_trades: dict[str, dict[str, deque[TradeEvent]]] = defaultdict(
            lambda: defaultdict(lambda: deque(maxlen=20000))
        )
        self.exchange_book_history: dict[str, dict[str, deque[BookTopEvent]]] = defaultdict(
            lambda: defaultdict(lambda: deque(maxlen=5000))
        )
        self.exchange_depth: dict[str, dict[str, OrderBookDepthEvent]] = defaultdict(dict)
        self.exchange_depth_history: dict[str, dict[str, deque[OrderBookDepthEvent]]] = defaultdict(
            lambda: defaultdict(lambda: deque(maxlen=1000))
        )
        self.book_history: dict[str, deque[BookTopEvent]] = {
            symbol: deque(maxlen=5000) for symbol in symbols
        }
        self.candles: dict[str, dict[str, CandleEvent]] = defaultdict(dict)
        self.candle_history: dict[str, dict[str, deque[CandleEvent]]] = {
            symbol: defaultdict(lambda: deque(maxlen=1500)) for symbol in symbols
        }
        self.trades: dict[str, deque[TradeEvent]] = {
            symbol: deque(maxlen=20000) for symbol in symbols
        }
        self.client_count = 0

    def mark_connected(self, connected: bool) -> None:
        self.connected = connected
        if not connected:
            self.reconnect_count += 1

    def apply(self, event: Union[TradeEvent, BookTopEvent, CandleEvent, OrderBookDepthEvent]) -> None:
        self.last_message_at = int(time.time() * 1000)
        self.message_counts[event.type] += 1
        if hasattr(event, "ingest_latency_ms"):
            self.last_latency_ms = event.ingest_latency_ms

        if isinstance(event, TradeEvent):
            self.exchange_latest_prices[event.exchange][event.symbol] = event.price
            self.exchange_trades[event.exchange][event.symbol].appendleft(event)
            if event.exchange == "binance":
                self.latest_prices[event.symbol] = event.price
                self.trades[event.symbol].appendleft(event)
        elif isinstance(event, BookTopEvent):
            self.exchange_books[event.exchange][event.symbol] = event
            self.exchange_book_history[event.exchange][event.symbol].appendleft(event)
            if event.exchange == "binance":
                self.books[event.symbol] = event
                self.book_history[event.symbol].appendleft(event)
        elif isinstance(event, CandleEvent):
            self.candles[event.symbol][event.interval] = event
            history = self.candle_history[event.symbol][event.interval]
            for index, candle in enumerate(history):
                if candle.open_time == event.open_time:
                    history[index] = event
                    break
            else:
                history.appendleft(event)
        elif isinstance(event, OrderBookDepthEvent):
            self.exchange_depth[event.exchange][event.symbol] = event
            self.exchange_depth_history[event.exchange][event.symbol].appendleft(event)

    def snapshot(self) -> dict[str, Any]:
        return {
            "type": "snapshot",
            "symbols": self.symbols,
            "prices": self.latest_prices,
            "books": {symbol: book.model_dump() for symbol, book in self.books.items()},
            "trades": {
                symbol: [trade.model_dump() for trade in trades]
                for symbol, trades in self.trades.items()
            },
            "candles": {
                symbol: {
                    interval: candle.model_dump()
                    for interval, candle in intervals.items()
                }
                for symbol, intervals in self.candles.items()
            },
            "health": self.health().model_dump(),
        }

    def exchange_snapshot(self) -> dict[str, Any]:
        return {
            "prices": {
                exchange: dict(symbols)
                for exchange, symbols in self.exchange_latest_prices.items()
            },
            "books": {
                exchange: {
                    symbol: book.model_dump()
                    for symbol, book in symbols.items()
                }
                for exchange, symbols in self.exchange_books.items()
            },
            "exchanges": sorted(
                set(self.exchange_latest_prices.keys()) | set(self.exchange_books.keys())
            ),
        }

    def health(self) -> HealthEvent:
        status = "healthy"
        now_ms = int(time.time() * 1000)
        if not self.connected:
            status = "unhealthy"
        elif self.last_message_at and now_ms - self.last_message_at > 10_000:
            status = "stale"
        elif self.last_message_at and now_ms - self.last_message_at > 3_000:
            status = "degraded"

        return HealthEvent(
            status=status,
            connected=self.connected,
            reconnect_count=self.reconnect_count,
            last_message_at=self.last_message_at,
            latency_ms=self.last_latency_ms,
            message_counts=dict(self.message_counts),
            client_count=self.client_count,
        )
