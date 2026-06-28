from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional, Union

import asyncpg

from app.config import settings
from app.schemas.market import BookTopEvent, CandleEvent, OrderBookDepthEvent, TradeEvent

logger = logging.getLogger(__name__)


def _dt(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def _decode_json_fields(row: dict[str, Any], *fields: str) -> dict[str, Any]:
    for field in fields:
        value = row.get(field)
        if isinstance(value, str):
            row[field] = json.loads(value)
    return row


class Database:
    def __init__(self) -> None:
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        if not settings.database_url:
            logger.warning("DATABASE_URL is not set; persistence disabled")
            return
        try:
            self.pool = await asyncpg.create_pool(settings.database_url, min_size=1, max_size=5)
            await self.ensure_schema()
            logger.info("database connected")
        except Exception:
            logger.exception("database connection failed; continuing without persistence")
            self.pool = None

    async def close(self) -> None:
        if self.pool:
            await self.pool.close()

    async def ensure_schema(self) -> None:
        if not self.pool:
            return
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS symbols (
                  id BIGSERIAL PRIMARY KEY,
                  symbol TEXT NOT NULL UNIQUE,
                  base_asset TEXT NOT NULL,
                  quote_asset TEXT NOT NULL,
                  exchange TEXT NOT NULL DEFAULT 'binance',
                  enabled BOOLEAN NOT NULL DEFAULT TRUE,
                  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );

                CREATE TABLE IF NOT EXISTS trades (
                  id BIGSERIAL PRIMARY KEY,
                  exchange TEXT NOT NULL,
                  symbol TEXT NOT NULL,
                  trade_id BIGINT NOT NULL,
                  price NUMERIC(20, 8) NOT NULL,
                  quantity NUMERIC(20, 8) NOT NULL,
                  buyer_maker BOOLEAN,
                  event_time TIMESTAMPTZ NOT NULL,
                  trade_time TIMESTAMPTZ NOT NULL,
                  received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                  ingest_latency_ms INTEGER,
                  UNIQUE(exchange, symbol, trade_id)
                );

                CREATE INDEX IF NOT EXISTS idx_trades_symbol_time
                ON trades(symbol, trade_time DESC);

                CREATE TABLE IF NOT EXISTS order_book_top (
                  id BIGSERIAL PRIMARY KEY,
                  exchange TEXT NOT NULL,
                  symbol TEXT NOT NULL,
                  bid_price NUMERIC(20, 8) NOT NULL,
                  bid_quantity NUMERIC(20, 8) NOT NULL,
                  ask_price NUMERIC(20, 8) NOT NULL,
                  ask_quantity NUMERIC(20, 8) NOT NULL,
                  spread NUMERIC(20, 8) NOT NULL,
                  spread_bps NUMERIC(20, 8),
                  event_time TIMESTAMPTZ,
                  received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                  ingest_latency_ms INTEGER
                );

                CREATE INDEX IF NOT EXISTS idx_order_book_top_symbol_time
                ON order_book_top(symbol, received_at DESC);

                CREATE TABLE IF NOT EXISTS candles (
                  id BIGSERIAL PRIMARY KEY,
                  exchange TEXT NOT NULL,
                  symbol TEXT NOT NULL,
                  interval TEXT NOT NULL,
                  open_time TIMESTAMPTZ NOT NULL,
                  close_time TIMESTAMPTZ NOT NULL,
                  open NUMERIC(20, 8) NOT NULL,
                  high NUMERIC(20, 8) NOT NULL,
                  low NUMERIC(20, 8) NOT NULL,
                  close NUMERIC(20, 8) NOT NULL,
                  volume NUMERIC(30, 8) NOT NULL,
                  quote_volume NUMERIC(30, 8),
                  trade_count INTEGER,
                  is_closed BOOLEAN NOT NULL,
                  received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                  UNIQUE(exchange, symbol, interval, open_time)
                );

                CREATE INDEX IF NOT EXISTS idx_candles_symbol_interval_time
                ON candles(symbol, interval, open_time DESC);

                CREATE TABLE IF NOT EXISTS ingestion_events (
                  id BIGSERIAL PRIMARY KEY,
                  exchange TEXT NOT NULL,
                  stream_name TEXT NOT NULL,
                  status TEXT NOT NULL,
                  message TEXT,
                  occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );

                CREATE TABLE IF NOT EXISTS analytics_events (
                  id BIGSERIAL PRIMARY KEY,
                  event_type TEXT NOT NULL,
                  exchange TEXT NOT NULL DEFAULT 'binance',
                  symbol TEXT NOT NULL,
                  severity TEXT NOT NULL DEFAULT 'info',
                  metric_name TEXT NOT NULL,
                  metric_value NUMERIC(30, 10),
                  baseline_value NUMERIC(30, 10),
                  metric_window TEXT,
                  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                  occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );

                CREATE INDEX IF NOT EXISTS idx_analytics_events_symbol_time
                ON analytics_events(symbol, occurred_at DESC);

                CREATE TABLE IF NOT EXISTS analytics_snapshots (
                  id BIGSERIAL PRIMARY KEY,
                  metric_family TEXT NOT NULL,
                  exchange TEXT NOT NULL DEFAULT 'binance',
                  metric_window TEXT,
                  payload JSONB NOT NULL,
                  computed_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );

                CREATE INDEX IF NOT EXISTS idx_analytics_snapshots_family_time
                ON analytics_snapshots(metric_family, computed_at DESC);

                CREATE INDEX IF NOT EXISTS idx_analytics_snapshots_family_window_time
                ON analytics_snapshots(metric_family, metric_window, computed_at DESC);

                INSERT INTO symbols(symbol, base_asset, quote_asset)
                VALUES
                  ('BTCUSDT', 'BTC', 'USDT'),
                  ('ETHUSDT', 'ETH', 'USDT'),
                  ('SOLUSDT', 'SOL', 'USDT')
                ON CONFLICT (symbol) DO NOTHING;
                """
            )

    async def save_trade(self, event: TradeEvent) -> None:
        if not self.pool:
            return
        await self.pool.execute(
            """
            INSERT INTO trades (
              exchange, symbol, trade_id, price, quantity, buyer_maker,
              event_time, trade_time, received_at, ingest_latency_ms
            )
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
            ON CONFLICT (exchange, symbol, trade_id) DO NOTHING
            """,
            event.exchange,
            event.symbol,
            event.trade_id,
            event.price,
            event.quantity,
            event.buyer_maker,
            _dt(event.event_time),
            _dt(event.trade_time),
            _dt(event.received_at),
            event.ingest_latency_ms,
        )

    async def save_book(self, event: BookTopEvent) -> None:
        if not self.pool:
            return
        await self.pool.execute(
            """
            INSERT INTO order_book_top (
              exchange, symbol, bid_price, bid_quantity, ask_price, ask_quantity,
              spread, spread_bps, event_time, received_at, ingest_latency_ms
            )
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
            """,
            event.exchange,
            event.symbol,
            event.bid_price,
            event.bid_quantity,
            event.ask_price,
            event.ask_quantity,
            event.spread,
            event.spread_bps,
            _dt(event.event_time),
            _dt(event.received_at),
            event.ingest_latency_ms,
        )

    async def save_candle(self, event: CandleEvent) -> None:
        if not self.pool:
            return
        await self.pool.execute(
            """
            INSERT INTO candles (
              exchange, symbol, interval, open_time, close_time, open, high, low,
              close, volume, quote_volume, trade_count, is_closed, received_at
            )
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
            ON CONFLICT (exchange, symbol, interval, open_time)
            DO UPDATE SET
              close_time = EXCLUDED.close_time,
              high = EXCLUDED.high,
              low = EXCLUDED.low,
              close = EXCLUDED.close,
              volume = EXCLUDED.volume,
              quote_volume = EXCLUDED.quote_volume,
              trade_count = EXCLUDED.trade_count,
              is_closed = EXCLUDED.is_closed,
              received_at = EXCLUDED.received_at
            """,
            event.exchange,
            event.symbol,
            event.interval,
            _dt(event.open_time),
            _dt(event.close_time),
            event.open,
            event.high,
            event.low,
            event.close,
            event.volume,
            event.quote_volume,
            event.trade_count,
            event.is_closed,
            _dt(event.received_at),
        )

    async def save_event(
        self, event: Union[TradeEvent, BookTopEvent, CandleEvent, OrderBookDepthEvent]
    ) -> None:
        try:
            if isinstance(event, TradeEvent):
                await self.save_trade(event)
            elif isinstance(event, BookTopEvent):
                await self.save_book(event)
            elif isinstance(event, CandleEvent):
                await self.save_candle(event)
            elif isinstance(event, OrderBookDepthEvent):
                return
        except Exception:
            logger.exception("failed to persist market event", extra={"type": event.type})

    async def save_analytics_snapshot(
        self, metric_family: str, payload: dict[str, Any], window: Optional[str] = None
    ) -> None:
        if not self.pool:
            return
        await self.pool.execute(
            """
            INSERT INTO analytics_snapshots(metric_family, exchange, metric_window, payload)
            VALUES ($1, 'binance', $2, $3::jsonb)
            """,
            metric_family,
            window,
            json.dumps(payload),
        )

    async def save_analytics_snapshots(self, snapshots: list[dict[str, Any]]) -> None:
        if not self.pool or not snapshots:
            return
        async with self.pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO analytics_snapshots(metric_family, exchange, metric_window, payload)
                VALUES ($1, $2, $3, $4::jsonb)
                """,
                [
                    (
                        snapshot["metric_family"],
                        snapshot.get("exchange", "binance"),
                        snapshot.get("window"),
                        json.dumps(snapshot.get("payload", {})),
                    )
                    for snapshot in snapshots
                ],
            )

    async def save_analytics_events(self, events: list[dict[str, Any]]) -> None:
        if not self.pool or not events:
            return
        async with self.pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO analytics_events(
                  event_type, exchange, symbol, severity, metric_name,
                  metric_value, baseline_value, metric_window, payload
                )
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb)
                """,
                [
                    (
                        event["event_type"],
                        event.get("exchange", "binance"),
                        event["symbol"],
                        event.get("severity", "info"),
                        event["metric_name"],
                        event.get("metric_value"),
                        event.get("baseline_value"),
                        event.get("window"),
                        json.dumps(event.get("payload", {})),
                    )
                    for event in events
                ],
            )

    async def fetch_analytics_events(self, limit: int = 50) -> list[dict[str, Any]]:
        if not self.pool:
            return []
        rows = await self.pool.fetch(
            """
            SELECT event_type, exchange, symbol, severity, metric_name, metric_value,
                   baseline_value, metric_window AS window, payload, occurred_at
            FROM analytics_events
            ORDER BY occurred_at DESC
            LIMIT $1
            """,
            limit,
        )
        return [_decode_json_fields(dict(row), "payload") for row in rows]

    async def fetch_latest_analytics_snapshot(
        self, metric_family: str = "summary"
    ) -> Optional[dict[str, Any]]:
        if not self.pool:
            return None
        row = await self.pool.fetchrow(
            """
            SELECT metric_family, exchange, metric_window AS window, payload, computed_at
            FROM analytics_snapshots
            WHERE metric_family = $1
            ORDER BY computed_at DESC
            LIMIT 1
            """,
            metric_family,
        )
        return _decode_json_fields(dict(row), "payload") if row else None

    async def fetch_analytics_history(
        self,
        metric_family: str,
        limit: int = 200,
        window: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        if not self.pool:
            return []
        if window:
            rows = await self.pool.fetch(
                """
                SELECT metric_family, exchange, metric_window AS window, payload, computed_at
                FROM analytics_snapshots
                WHERE metric_family = $1 AND metric_window = $2
                ORDER BY computed_at DESC
                LIMIT $3
                """,
                metric_family,
                window,
                limit,
            )
        else:
            rows = await self.pool.fetch(
                """
                SELECT metric_family, exchange, metric_window AS window, payload, computed_at
                FROM analytics_snapshots
                WHERE metric_family = $1
                ORDER BY computed_at DESC
                LIMIT $2
                """,
                metric_family,
                limit,
            )
        return [_decode_json_fields(dict(row), "payload") for row in reversed(rows)]
