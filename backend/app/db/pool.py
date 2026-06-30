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
        self._last_book_persist_ms: dict[tuple[str, str], int] = {}

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

    async def ping(self) -> bool:
        if not self.pool:
            return False
        try:
            await self.pool.fetchval("SELECT 1")
            return True
        except Exception:
            logger.exception("database ping failed")
            return False

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

                CREATE INDEX IF NOT EXISTS idx_trades_trade_time
                ON trades(trade_time);

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

                CREATE INDEX IF NOT EXISTS idx_order_book_top_received_at
                ON order_book_top(received_at);

                CREATE TABLE IF NOT EXISTS order_book_rollups (
                  id BIGSERIAL PRIMARY KEY,
                  exchange TEXT NOT NULL,
                  symbol TEXT NOT NULL,
                  bucket_start TIMESTAMPTZ NOT NULL,
                  bucket_minutes INTEGER NOT NULL DEFAULT 1,
                  sample_count INTEGER NOT NULL,
                  avg_bid_price NUMERIC(20, 8),
                  avg_ask_price NUMERIC(20, 8),
                  avg_mid_price NUMERIC(20, 8),
                  avg_spread_bps NUMERIC(20, 8),
                  min_spread_bps NUMERIC(20, 8),
                  max_spread_bps NUMERIC(20, 8),
                  avg_bid_quantity NUMERIC(30, 8),
                  avg_ask_quantity NUMERIC(30, 8),
                  avg_top_bid_notional NUMERIC(30, 8),
                  avg_top_ask_notional NUMERIC(30, 8),
                  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                  UNIQUE(exchange, symbol, bucket_minutes, bucket_start)
                );

                CREATE INDEX IF NOT EXISTS idx_order_book_rollups_symbol_time
                ON order_book_rollups(symbol, bucket_start DESC);

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

                CREATE INDEX IF NOT EXISTS idx_candles_open_time
                ON candles(open_time);

                CREATE TABLE IF NOT EXISTS ingestion_events (
                  id BIGSERIAL PRIMARY KEY,
                  exchange TEXT NOT NULL,
                  stream_name TEXT NOT NULL,
                  status TEXT NOT NULL,
                  message TEXT,
                  occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );

                CREATE TABLE IF NOT EXISTS system_events (
                  id BIGSERIAL PRIMARY KEY,
                  component TEXT NOT NULL,
                  event_type TEXT NOT NULL,
                  severity TEXT NOT NULL DEFAULT 'info',
                  status TEXT,
                  message TEXT,
                  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                  occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );

                CREATE INDEX IF NOT EXISTS idx_system_events_time
                ON system_events(occurred_at DESC);

                CREATE INDEX IF NOT EXISTS idx_system_events_component_time
                ON system_events(component, occurred_at DESC);

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

                CREATE INDEX IF NOT EXISTS idx_analytics_events_occurred_at
                ON analytics_events(occurred_at);

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

                CREATE INDEX IF NOT EXISTS idx_analytics_snapshots_computed_at
                ON analytics_snapshots(computed_at);

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
        throttle_ms = max(0, settings.order_book_persist_interval_ms)
        key = (event.exchange, event.symbol)
        last_persisted_at = self._last_book_persist_ms.get(key, 0)
        if throttle_ms and event.received_at - last_persisted_at < throttle_ms:
            return
        self._last_book_persist_ms[key] = event.received_at
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

    async def table_stats(self) -> list[dict[str, Any]]:
        if not self.pool:
            return []
        rows = await self.pool.fetch(
            """
            SELECT
              relname AS table_name,
              n_live_tup::bigint AS estimated_rows,
              pg_total_relation_size(relid)::bigint AS total_bytes
            FROM pg_stat_user_tables
            WHERE relname IN (
              'trades',
              'order_book_top',
              'order_book_rollups',
              'candles',
              'system_events',
              'analytics_events',
              'analytics_snapshots'
            )
            ORDER BY pg_total_relation_size(relid) DESC
            """
        )
        return [dict(row) for row in rows]

    async def record_system_event(
        self,
        component: str,
        event_type: str,
        *,
        severity: str = "info",
        status: Optional[str] = None,
        message: Optional[str] = None,
        payload: Optional[dict[str, Any]] = None,
    ) -> None:
        if not self.pool:
            return
        try:
            await self.pool.execute(
                """
                INSERT INTO system_events(component, event_type, severity, status, message, payload)
                VALUES ($1,$2,$3,$4,$5,$6::jsonb)
                """,
                component,
                event_type,
                severity,
                status,
                message,
                json.dumps(payload or {}),
            )
        except Exception:
            logger.exception(
                "failed to record system event",
                extra={"component": component, "event_type": event_type},
            )

    async def fetch_system_events(
        self,
        limit: int = 100,
        component: Optional[str] = None,
        severity: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        if not self.pool:
            return []
        conditions = []
        values: list[Any] = []
        if component:
            values.append(component)
            conditions.append(f"component = ${len(values)}")
        if severity:
            values.append(severity)
            conditions.append(f"severity = ${len(values)}")
        values.append(limit)
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = await self.pool.fetch(
            f"""
            SELECT component, event_type, severity, status, message, payload, occurred_at
            FROM system_events
            {where_clause}
            ORDER BY occurred_at DESC
            LIMIT ${len(values)}
            """,
            *values,
        )
        return [_decode_json_fields(dict(row), "payload") for row in rows]

    async def fetch_storage_summary(self) -> dict[str, Any]:
        stats = await self.table_stats()
        if not self.pool:
            return {"tables": stats, "rollups": []}
        rows = await self.pool.fetch(
            """
            SELECT
              exchange,
              symbol,
              bucket_minutes,
              count(*)::bigint AS bucket_count,
              min(bucket_start) AS first_bucket,
              max(bucket_start) AS last_bucket
            FROM order_book_rollups
            GROUP BY exchange, symbol, bucket_minutes
            ORDER BY exchange, symbol, bucket_minutes
            """
        )
        return {
            "tables": stats,
            "rollups": [dict(row) for row in rows],
        }

    async def refresh_order_book_rollups(self) -> dict[str, int]:
        if not self.pool or not settings.rollups_enabled:
            return {}
        bucket_minutes = settings.order_book_rollup_bucket_minutes
        if bucket_minutes != 1:
            logger.warning("only 1-minute order book rollups are currently supported")
            bucket_minutes = 1

        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                INSERT INTO order_book_rollups (
                  exchange,
                  symbol,
                  bucket_start,
                  bucket_minutes,
                  sample_count,
                  avg_bid_price,
                  avg_ask_price,
                  avg_mid_price,
                  avg_spread_bps,
                  min_spread_bps,
                  max_spread_bps,
                  avg_bid_quantity,
                  avg_ask_quantity,
                  avg_top_bid_notional,
                  avg_top_ask_notional,
                  updated_at
                )
                SELECT
                  exchange,
                  symbol,
                  date_trunc('minute', received_at) AS bucket_start,
                  $1::int AS bucket_minutes,
                  count(*)::int AS sample_count,
                  avg(bid_price),
                  avg(ask_price),
                  avg((bid_price + ask_price) / 2),
                  avg(spread_bps),
                  min(spread_bps),
                  max(spread_bps),
                  avg(bid_quantity),
                  avg(ask_quantity),
                  avg(bid_price * bid_quantity),
                  avg(ask_price * ask_quantity),
                  now()
                FROM order_book_top
                WHERE received_at >= now() - ($2::int * interval '1 hour')
                  AND received_at < date_trunc('minute', now())
                GROUP BY exchange, symbol, date_trunc('minute', received_at)
                ON CONFLICT (exchange, symbol, bucket_minutes, bucket_start)
                DO UPDATE SET
                  sample_count = EXCLUDED.sample_count,
                  avg_bid_price = EXCLUDED.avg_bid_price,
                  avg_ask_price = EXCLUDED.avg_ask_price,
                  avg_mid_price = EXCLUDED.avg_mid_price,
                  avg_spread_bps = EXCLUDED.avg_spread_bps,
                  min_spread_bps = EXCLUDED.min_spread_bps,
                  max_spread_bps = EXCLUDED.max_spread_bps,
                  avg_bid_quantity = EXCLUDED.avg_bid_quantity,
                  avg_ask_quantity = EXCLUDED.avg_ask_quantity,
                  avg_top_bid_notional = EXCLUDED.avg_top_bid_notional,
                  avg_top_ask_notional = EXCLUDED.avg_top_ask_notional,
                  updated_at = now()
                """,
                bucket_minutes,
                settings.rollup_lookback_hours,
            )
        return {"order_book_rollups": int(result.rsplit(" ", 1)[-1])}

    async def fetch_order_book_rollups(
        self,
        symbol: Optional[str] = None,
        exchange: Optional[str] = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        if not self.pool:
            return []
        conditions = []
        values: list[Any] = []
        if symbol:
            values.append(symbol.upper())
            conditions.append(f"symbol = ${len(values)}")
        if exchange:
            values.append(exchange.lower())
            conditions.append(f"exchange = ${len(values)}")
        values.append(limit)
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = await self.pool.fetch(
            f"""
            SELECT
              exchange,
              symbol,
              bucket_start,
              bucket_minutes,
              sample_count,
              avg_bid_price,
              avg_ask_price,
              avg_mid_price,
              avg_spread_bps,
              min_spread_bps,
              max_spread_bps,
              avg_bid_quantity,
              avg_ask_quantity,
              avg_top_bid_notional,
              avg_top_ask_notional,
              updated_at
            FROM order_book_rollups
            {where_clause}
            ORDER BY bucket_start DESC
            LIMIT ${len(values)}
            """,
            *values,
        )
        return [dict(row) for row in reversed(rows)]

    async def apply_retention(self) -> dict[str, int]:
        if not self.pool or not settings.retention_enabled:
            return {}

        cleanup_specs = [
            ("trades", "trade_time", settings.trades_retention_days),
            ("order_book_top", "received_at", settings.order_book_retention_days),
            ("candles", "open_time", settings.candles_retention_days),
            ("analytics_events", "occurred_at", settings.analytics_events_retention_days),
            ("analytics_snapshots", "computed_at", settings.analytics_snapshots_retention_days),
            ("system_events", "occurred_at", settings.system_events_retention_days),
        ]
        deleted: dict[str, int] = {}
        async with self.pool.acquire() as conn:
            for table_name, timestamp_column, retention_days in cleanup_specs:
                if retention_days <= 0:
                    continue
                result = await conn.execute(
                    f"""
                    DELETE FROM {table_name}
                    WHERE id IN (
                      SELECT id
                      FROM {table_name}
                      WHERE {timestamp_column} < now() - ($1::int * interval '1 day')
                      ORDER BY {timestamp_column}
                      LIMIT $2
                    )
                    """,
                    retention_days,
                    settings.retention_delete_limit,
                )
                deleted[table_name] = int(result.rsplit(" ", 1)[-1])
        return deleted
