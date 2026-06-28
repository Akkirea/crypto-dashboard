from __future__ import annotations

from typing import Literal
from typing import Optional

from pydantic import BaseModel


class TradeEvent(BaseModel):
    type: Literal["trade"] = "trade"
    exchange: str = "binance"
    symbol: str
    trade_id: int
    price: float
    quantity: float
    buyer_maker: bool
    event_time: int
    trade_time: int
    received_at: int
    ingest_latency_ms: Optional[int] = None


class BookTopEvent(BaseModel):
    type: Literal["book_top"] = "book_top"
    exchange: str = "binance"
    symbol: str
    bid_price: float
    bid_quantity: float
    ask_price: float
    ask_quantity: float
    spread: float
    spread_bps: Optional[float]
    event_time: int
    received_at: int
    ingest_latency_ms: Optional[int] = None


class BookLevel(BaseModel):
    price: float
    quantity: float


class OrderBookDepthEvent(BaseModel):
    type: Literal["order_book_depth"] = "order_book_depth"
    exchange: str = "binance"
    symbol: str
    bids: list[BookLevel]
    asks: list[BookLevel]
    event_time: int
    received_at: int
    update_id: Optional[int] = None
    ingest_latency_ms: Optional[int] = None


class CandleEvent(BaseModel):
    type: Literal["candle"] = "candle"
    exchange: str = "binance"
    symbol: str
    interval: str
    open_time: int
    close_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: float
    trade_count: int
    is_closed: bool
    received_at: int


class HealthEvent(BaseModel):
    type: Literal["health"] = "health"
    status: str
    connected: bool
    reconnect_count: int
    last_message_at: Optional[int]
    latency_ms: Optional[int]
    message_counts: dict[str, int]
    client_count: int
