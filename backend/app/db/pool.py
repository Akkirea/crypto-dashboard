from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
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


def _experiment_validation(pnl: dict[str, Any]) -> dict[str, Any]:
    trades = int(pnl.get("closed_trade_count") or 0)
    net_pnl = Decimal(str(pnl.get("net_realized_pnl") or 0))
    profit_factor = pnl.get("profit_factor")
    pf = Decimal(str(profit_factor)) if profit_factor is not None else None
    if trades < 30:
        return {
            "status": "collecting",
            "reason": "needs_at_least_30_closed_trades_for_initial_read",
            "required_trades": 30,
        }
    if net_pnl <= 0:
        return {"status": "failing", "reason": "net_pnl_not_positive", "required_trades": 30}
    if pf is not None and pf < Decimal("1.3"):
        return {"status": "weak", "reason": "profit_factor_below_1_3", "required_trades": 30}
    return {"status": "promising", "reason": "initial_forward_test_thresholds_met", "required_trades": 30}


def _experiment_scorecard(pnl: dict[str, Any]) -> dict[str, Any]:
    trades = int(pnl.get("closed_trade_count") or 0)
    wins = int(pnl.get("winning_trade_count") or 0)
    losses = int(pnl.get("losing_trade_count") or 0)
    gross_realized = Decimal(str(pnl.get("gross_realized_pnl") or 0))
    fees = Decimal(str(pnl.get("total_fees") or 0))
    net_realized = Decimal(str(pnl.get("net_realized_pnl") or 0))
    win_rate = pnl.get("win_rate_pct")
    profit_factor = pnl.get("profit_factor")
    expectancy = net_realized / Decimal(trades) if trades else None
    fee_drag_pct = (fees / abs(gross_realized) * Decimal("100")) if gross_realized else None
    return {
        "closed_trades": trades,
        "wins": wins,
        "losses": losses,
        "expectancy_per_trade": expectancy,
        "net_realized_pnl": net_realized,
        "fees": fees,
        "fee_drag_pct": fee_drag_pct,
        "win_rate_pct": win_rate,
        "profit_factor": profit_factor,
    }


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


class Database:
    def __init__(self) -> None:
        self.pool: Optional[asyncpg.Pool] = None
        self._last_book_persist_ms: dict[tuple[str, str], int] = {}
        self._connect_lock = asyncio.Lock()

    async def connect(self) -> None:
        if not settings.database_url:
            logger.warning("DATABASE_URL is not set; persistence disabled")
            return
        async with self._connect_lock:
            if self.pool:
                return
            try:
                self.pool = await asyncpg.create_pool(
                    settings.database_url,
                    min_size=1,
                    max_size=5,
                    timeout=settings.database_connect_timeout_seconds,
                )
                await self.ensure_schema()
                logger.info("database connected")
            except Exception:
                logger.exception("database connection failed; continuing without persistence")
                if self.pool:
                    await self.pool.close()
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
            if self.pool:
                await self.pool.close()
            self.pool = None
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

                CREATE TABLE IF NOT EXISTS simulation_portfolios (
                  id TEXT PRIMARY KEY,
                  cash_balance NUMERIC(30, 8) NOT NULL,
                  initial_cash NUMERIC(30, 8) NOT NULL,
                  realized_pnl NUMERIC(30, 8) NOT NULL DEFAULT 0,
                  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );

                CREATE TABLE IF NOT EXISTS simulation_orders (
                  id BIGSERIAL PRIMARY KEY,
                  experiment_id BIGINT,
                  portfolio_id TEXT NOT NULL REFERENCES simulation_portfolios(id),
                  exchange TEXT NOT NULL,
                  symbol TEXT NOT NULL,
                  side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
                  order_type TEXT NOT NULL CHECK (order_type IN ('market')),
                  status TEXT NOT NULL CHECK (
                    status IN ('submitted', 'filled', 'rejected', 'cancelled')
                  ),
                  requested_quantity NUMERIC(30, 8) NOT NULL,
                  filled_quantity NUMERIC(30, 8) NOT NULL DEFAULT 0,
                  fill_price NUMERIC(30, 8),
                  fee NUMERIC(30, 8) NOT NULL DEFAULT 0,
                  submitted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                  filled_at TIMESTAMPTZ,
                  rejection_reason TEXT,
                  payload JSONB NOT NULL DEFAULT '{}'::jsonb
                );

                CREATE INDEX IF NOT EXISTS idx_simulation_orders_portfolio_time
                ON simulation_orders(portfolio_id, submitted_at DESC);

                CREATE TABLE IF NOT EXISTS simulation_fills (
                  id BIGSERIAL PRIMARY KEY,
                  order_id BIGINT NOT NULL REFERENCES simulation_orders(id),
                  experiment_id BIGINT,
                  portfolio_id TEXT NOT NULL REFERENCES simulation_portfolios(id),
                  exchange TEXT NOT NULL,
                  symbol TEXT NOT NULL,
                  side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
                  price NUMERIC(30, 8) NOT NULL,
                  quantity NUMERIC(30, 8) NOT NULL,
                  notional NUMERIC(30, 8) NOT NULL,
                  fee NUMERIC(30, 8) NOT NULL,
                  liquidity TEXT NOT NULL DEFAULT 'taker',
                  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );

                CREATE INDEX IF NOT EXISTS idx_simulation_fills_portfolio_time
                ON simulation_fills(portfolio_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS simulation_positions (
                  portfolio_id TEXT NOT NULL REFERENCES simulation_portfolios(id),
                  exchange TEXT NOT NULL,
                  symbol TEXT NOT NULL,
                  quantity NUMERIC(30, 8) NOT NULL,
                  avg_entry_price NUMERIC(30, 8) NOT NULL,
                  realized_pnl NUMERIC(30, 8) NOT NULL DEFAULT 0,
                  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                  PRIMARY KEY (portfolio_id, exchange, symbol)
                );

                CREATE TABLE IF NOT EXISTS simulation_equity_snapshots (
                  id BIGSERIAL PRIMARY KEY,
                  portfolio_id TEXT NOT NULL REFERENCES simulation_portfolios(id),
                  cash_balance NUMERIC(30, 8) NOT NULL,
                  equity NUMERIC(30, 8) NOT NULL,
                  unrealized_pnl NUMERIC(30, 8) NOT NULL,
                  realized_pnl NUMERIC(30, 8) NOT NULL,
                  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );

                CREATE INDEX IF NOT EXISTS idx_simulation_equity_portfolio_time
                ON simulation_equity_snapshots(portfolio_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS simulation_backtest_runs (
                  id BIGSERIAL PRIMARY KEY,
                  exchange TEXT NOT NULL,
                  symbol TEXT NOT NULL,
                  interval TEXT NOT NULL,
                  strategy TEXT NOT NULL,
                  status TEXT NOT NULL DEFAULT 'completed',
                  parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
                  sample JSONB NOT NULL DEFAULT '{}'::jsonb,
                  summary JSONB NOT NULL DEFAULT '{}'::jsonb,
                  equity_curve JSONB NOT NULL DEFAULT '[]'::jsonb,
                  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );

                CREATE INDEX IF NOT EXISTS idx_simulation_backtest_runs_time
                ON simulation_backtest_runs(created_at DESC);

                CREATE INDEX IF NOT EXISTS idx_simulation_backtest_runs_symbol_time
                ON simulation_backtest_runs(symbol, created_at DESC);

                CREATE TABLE IF NOT EXISTS simulation_backtest_trades (
                  id BIGSERIAL PRIMARY KEY,
                  run_id BIGINT NOT NULL REFERENCES simulation_backtest_runs(id) ON DELETE CASCADE,
                  trade_time TIMESTAMPTZ NOT NULL,
                  side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
                  price NUMERIC(30, 8) NOT NULL,
                  quantity NUMERIC(30, 8) NOT NULL,
                  notional NUMERIC(30, 8) NOT NULL,
                  fee NUMERIC(30, 8) NOT NULL,
                  realized_pnl NUMERIC(30, 8) NOT NULL,
                  reason TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_simulation_backtest_trades_run_time
                ON simulation_backtest_trades(run_id, trade_time);

                CREATE TABLE IF NOT EXISTS simulation_strategy_signals (
                  id BIGSERIAL PRIMARY KEY,
                  experiment_id BIGINT,
                  portfolio_id TEXT NOT NULL,
                  exchange TEXT NOT NULL,
                  symbol TEXT NOT NULL,
                  strategy TEXT NOT NULL,
                  signal TEXT NOT NULL,
                  status TEXT NOT NULL,
                  reason TEXT,
                  candle_time TIMESTAMPTZ,
                  order_id BIGINT REFERENCES simulation_orders(id),
                  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );

                CREATE INDEX IF NOT EXISTS idx_simulation_strategy_signals_time
                ON simulation_strategy_signals(created_at DESC);

                CREATE INDEX IF NOT EXISTS idx_simulation_strategy_signals_symbol_time
                ON simulation_strategy_signals(symbol, created_at DESC);

                CREATE TABLE IF NOT EXISTS simulation_experiments (
                  id BIGSERIAL PRIMARY KEY,
                  portfolio_id TEXT NOT NULL REFERENCES simulation_portfolios(id),
                  exchange TEXT NOT NULL,
                  symbol TEXT NOT NULL,
                  interval TEXT NOT NULL,
                  strategy TEXT NOT NULL,
                  status TEXT NOT NULL DEFAULT 'running'
                    CHECK (status IN ('running', 'completed', 'stopped')),
                  parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
                  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                  ended_at TIMESTAMPTZ,
                  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );

                CREATE INDEX IF NOT EXISTS idx_simulation_experiments_time
                ON simulation_experiments(started_at DESC);

                CREATE INDEX IF NOT EXISTS idx_simulation_experiments_status
                ON simulation_experiments(status, started_at DESC);

                ALTER TABLE simulation_orders
                ADD COLUMN IF NOT EXISTS experiment_id BIGINT REFERENCES simulation_experiments(id);

                ALTER TABLE simulation_fills
                ADD COLUMN IF NOT EXISTS experiment_id BIGINT REFERENCES simulation_experiments(id);

                ALTER TABLE simulation_strategy_signals
                ADD COLUMN IF NOT EXISTS experiment_id BIGINT REFERENCES simulation_experiments(id);

                CREATE INDEX IF NOT EXISTS idx_simulation_orders_experiment_time
                ON simulation_orders(experiment_id, submitted_at DESC);

                CREATE INDEX IF NOT EXISTS idx_simulation_fills_experiment_time
                ON simulation_fills(experiment_id, created_at DESC);

                CREATE INDEX IF NOT EXISTS idx_simulation_signals_experiment_time
                ON simulation_strategy_signals(experiment_id, created_at DESC);

                INSERT INTO symbols(symbol, base_asset, quote_asset)
                VALUES
                  ('BTCUSDT', 'BTC', 'USDT'),
                  ('ETHUSDT', 'ETH', 'USDT'),
                  ('SOLUSDT', 'SOL', 'USDT')
                ON CONFLICT (symbol) DO NOTHING;
                """,
            )
            await conn.execute(
                """
                INSERT INTO simulation_portfolios(id, cash_balance, initial_cash)
                VALUES ('default', $1, $1)
                ON CONFLICT (id) DO NOTHING;
                """,
                Decimal(str(settings.simulation_initial_cash)),
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
              'analytics_snapshots',
              'simulation_portfolios',
              'simulation_orders',
              'simulation_fills',
              'simulation_positions',
              'simulation_equity_snapshots',
              'simulation_backtest_runs',
              'simulation_backtest_trades',
              'simulation_strategy_signals'
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

    async def fetch_recent_trades(
        self,
        symbol: str,
        *,
        exchange: str = "binance",
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        if not self.pool:
            return []
        rows = await self.pool.fetch(
            """
            SELECT exchange, symbol, trade_id, price, quantity, buyer_maker,
                   event_time, trade_time, received_at, ingest_latency_ms
            FROM trades
            WHERE exchange = $1 AND symbol = $2
            ORDER BY trade_time DESC
            LIMIT $3
            """,
            exchange.lower(),
            symbol.upper(),
            limit,
        )
        return [dict(row) for row in reversed(rows)]

    async def fetch_recent_candles(
        self,
        symbol: str,
        interval: str,
        *,
        exchange: str = "binance",
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        if not self.pool:
            return []
        rows = await self.pool.fetch(
            """
            SELECT exchange, symbol, interval, open_time, close_time,
                   open, high, low, close, volume, quote_volume,
                   trade_count, is_closed, received_at
            FROM candles
            WHERE exchange = $1 AND symbol = $2 AND interval = $3
            ORDER BY open_time DESC
            LIMIT $4
            """,
            exchange.lower(),
            symbol.upper(),
            interval,
            limit,
        )
        return [dict(row) for row in reversed(rows)]

    async def fetch_backtest_candles(
        self,
        symbol: str,
        interval: str,
        *,
        exchange: str = "binance",
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        if not self.pool:
            return []
        rows = await self.pool.fetch(
            """
            SELECT exchange, symbol, interval, open_time, close_time,
                   open, high, low, close, volume, quote_volume,
                   trade_count, is_closed, received_at
            FROM candles
            WHERE exchange = $1
              AND symbol = $2
              AND interval = $3
              AND is_closed = true
            ORDER BY open_time DESC
            LIMIT $4
            """,
            exchange.lower(),
            symbol.upper(),
            interval,
            limit,
        )
        return [dict(row) for row in reversed(rows)]

    async def save_backtest_run(
        self,
        result: dict[str, Any],
        *,
        exchange: str = "binance",
    ) -> Optional[dict[str, Any]]:
        if not self.pool:
            return None
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                run = await conn.fetchrow(
                    """
                    INSERT INTO simulation_backtest_runs(
                      exchange, symbol, interval, strategy, status,
                      parameters, sample, summary, equity_curve
                    )
                    VALUES ($1,$2,$3,$4,'completed',$5::jsonb,$6::jsonb,$7::jsonb,$8::jsonb)
                    RETURNING id, exchange, symbol, interval, strategy, status,
                              parameters, sample, summary, equity_curve, created_at
                    """,
                    exchange.lower(),
                    result["symbol"],
                    result["interval"],
                    result["strategy"],
                    json.dumps(result.get("parameters", {}), default=_json_default),
                    json.dumps(result.get("sample", {}), default=_json_default),
                    json.dumps(result.get("summary", {}), default=_json_default),
                    json.dumps(result.get("equity_curve", []), default=_json_default),
                )
                trades = result.get("trades", [])
                if trades:
                    await conn.executemany(
                        """
                        INSERT INTO simulation_backtest_trades(
                          run_id, trade_time, side, price, quantity,
                          notional, fee, realized_pnl, reason
                        )
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                        """,
                        [
                            (
                                run["id"],
                                trade["time"],
                                trade["side"],
                                Decimal(str(trade["price"])),
                                Decimal(str(trade["quantity"])),
                                Decimal(str(trade["notional"])),
                                Decimal(str(trade["fee"])),
                                Decimal(str(trade["realized_pnl"])),
                                trade["reason"],
                            )
                            for trade in trades
                        ],
                    )
        saved = _decode_json_fields(dict(run), "parameters", "sample", "summary", "equity_curve")
        saved["trade_count"] = len(result.get("trades", []))
        return saved

    async def fetch_backtest_runs(
        self,
        *,
        symbol: Optional[str] = None,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        if not self.pool:
            return []
        values: list[Any] = []
        where_clause = ""
        if symbol:
            values.append(symbol.upper())
            where_clause = f"WHERE symbol = ${len(values)}"
        values.append(limit)
        rows = await self.pool.fetch(
            f"""
            SELECT
              r.id,
              r.exchange,
              r.symbol,
              r.interval,
              r.strategy,
              r.status,
              r.parameters,
              r.sample,
              r.summary,
              r.created_at,
              count(t.id)::int AS trade_count
            FROM simulation_backtest_runs r
            LEFT JOIN simulation_backtest_trades t ON t.run_id = r.id
            {where_clause}
            GROUP BY r.id
            ORDER BY r.created_at DESC
            LIMIT ${len(values)}
            """,
            *values,
        )
        return [
            _decode_json_fields(dict(row), "parameters", "sample", "summary")
            for row in rows
        ]

    async def fetch_backtest_run(self, run_id: int) -> Optional[dict[str, Any]]:
        if not self.pool:
            return None
        async with self.pool.acquire() as conn:
            run = await conn.fetchrow(
                """
                SELECT id, exchange, symbol, interval, strategy, status,
                       parameters, sample, summary, equity_curve, created_at
                FROM simulation_backtest_runs
                WHERE id = $1
                """,
                run_id,
            )
            if not run:
                return None
            trades = await conn.fetch(
                """
                SELECT id, run_id, trade_time AS time, side, price, quantity,
                       notional, fee, realized_pnl, reason
                FROM simulation_backtest_trades
                WHERE run_id = $1
                ORDER BY trade_time
                """,
                run_id,
            )
        payload = _decode_json_fields(dict(run), "parameters", "sample", "summary", "equity_curve")
        payload["trades"] = [dict(row) for row in trades]
        payload["type"] = "backtest_result"
        payload["read_only"] = True
        return payload

    async def fetch_latest_book_top(
        self,
        symbol: str,
        *,
        exchange: str = "binance",
    ) -> Optional[dict[str, Any]]:
        if not self.pool:
            return None
        row = await self.pool.fetchrow(
            """
            SELECT exchange, symbol, bid_price, bid_quantity, ask_price, ask_quantity,
                   spread, spread_bps, event_time, received_at, ingest_latency_ms
            FROM order_book_top
            WHERE exchange = $1 AND symbol = $2
            ORDER BY received_at DESC
            LIMIT 1
            """,
            exchange.lower(),
            symbol.upper(),
        )
        return dict(row) if row else None

    async def save_strategy_signal(
        self,
        *,
        experiment_id: Optional[int] = None,
        portfolio_id: str,
        exchange: str,
        symbol: str,
        strategy: str,
        signal: str,
        status: str,
        reason: Optional[str] = None,
        candle_time: Optional[datetime] = None,
        order_id: Optional[int] = None,
        payload: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        if not self.pool:
            return None
        row = await self.pool.fetchrow(
            """
            INSERT INTO simulation_strategy_signals(
              experiment_id, portfolio_id, exchange, symbol, strategy, signal, status,
              reason, candle_time, order_id, payload
            )
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11::jsonb)
            RETURNING id, experiment_id, portfolio_id, exchange, symbol, strategy, signal,
                      status, reason, candle_time, order_id, payload, created_at
            """,
            experiment_id,
            portfolio_id,
            exchange.lower(),
            symbol.upper(),
            strategy,
            signal,
            status,
            reason,
            candle_time,
            order_id,
            json.dumps(payload or {}, default=_json_default),
        )
        return _decode_json_fields(dict(row), "payload")

    async def fetch_strategy_signals(
        self,
        *,
        portfolio_id: str = "default",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if not self.pool:
            return []
        rows = await self.pool.fetch(
            """
            SELECT id, experiment_id, portfolio_id, exchange, symbol, strategy, signal,
                   status, reason, candle_time, order_id, payload, created_at
            FROM simulation_strategy_signals
            WHERE portfolio_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            portfolio_id,
            limit,
        )
        return [_decode_json_fields(dict(row), "payload") for row in rows]

    async def fetch_simulation_orders(
        self, portfolio_id: str = "default", limit: int = 100
    ) -> list[dict[str, Any]]:
        if not self.pool:
            return []
        rows = await self.pool.fetch(
            """
            SELECT id, experiment_id, portfolio_id, exchange, symbol, side, order_type, status,
                   requested_quantity, filled_quantity, fill_price, fee,
                   submitted_at, filled_at, rejection_reason, payload
            FROM simulation_orders
            WHERE portfolio_id = $1
            ORDER BY submitted_at DESC
            LIMIT $2
            """,
            portfolio_id,
            limit,
        )
        return [_decode_json_fields(dict(row), "payload") for row in rows]

    async def fetch_simulation_fills(
        self, portfolio_id: str = "default", limit: int = 100
    ) -> list[dict[str, Any]]:
        if not self.pool:
            return []
        rows = await self.pool.fetch(
            """
            SELECT id, order_id, experiment_id, portfolio_id, exchange, symbol, side, price,
                   quantity, notional, fee, liquidity, created_at
            FROM simulation_fills
            WHERE portfolio_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            portfolio_id,
            limit,
        )
        return [dict(row) for row in rows]

    async def fetch_simulation_fills_for_pnl(
        self,
        portfolio_id: str = "default",
        limit: int = 1000,
        experiment_id: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        if not self.pool:
            return []
        if experiment_id is None:
            return await self.fetch_simulation_fills(portfolio_id=portfolio_id, limit=limit)
        rows = await self.pool.fetch(
            """
            SELECT id, order_id, experiment_id, portfolio_id, exchange, symbol, side, price,
                   quantity, notional, fee, liquidity, created_at
            FROM simulation_fills
            WHERE portfolio_id = $1 AND experiment_id = $2
            ORDER BY created_at DESC
            LIMIT $3
            """,
            portfolio_id,
            experiment_id,
            limit,
        )
        return [dict(row) for row in rows]

    async def fetch_simulation_experiment_open_quantity(
        self,
        *,
        portfolio_id: str = "default",
        experiment_id: Optional[int],
        exchange: str,
        symbol: str,
    ) -> Decimal:
        if not self.pool or experiment_id is None:
            return Decimal("0")
        rows = await self.pool.fetch(
            """
            SELECT side, quantity
            FROM simulation_fills
            WHERE portfolio_id = $1
              AND experiment_id = $2
              AND exchange = $3
              AND symbol = $4
            ORDER BY created_at
            """,
            portfolio_id,
            experiment_id,
            exchange.lower(),
            symbol.upper(),
        )
        open_qty = Decimal("0")
        for row in rows:
            quantity = Decimal(row["quantity"])
            if row["side"] == "buy":
                open_qty += quantity
            else:
                open_qty = max(Decimal("0"), open_qty - quantity)
        return open_qty

    async def create_simulation_experiment(
        self,
        *,
        portfolio_id: str,
        exchange: str,
        symbol: str,
        interval: str,
        strategy: str,
        parameters: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        if not self.pool:
            return None
        await self._ensure_simulation_portfolio(portfolio_id)
        row = await self.pool.fetchrow(
            """
            INSERT INTO simulation_experiments(
              portfolio_id, exchange, symbol, interval, strategy, status, parameters
            )
            VALUES ($1,$2,$3,$4,$5,'running',$6::jsonb)
            RETURNING id, portfolio_id, exchange, symbol, interval, strategy, status,
                      parameters, started_at, ended_at, created_at, updated_at
            """,
            portfolio_id,
            exchange.lower(),
            symbol.upper(),
            interval,
            strategy,
            json.dumps(parameters, default=_json_default),
        )
        return _decode_json_fields(dict(row), "parameters")

    async def end_simulation_experiment(self, experiment_id: int) -> Optional[dict[str, Any]]:
        if not self.pool:
            return None
        row = await self.pool.fetchrow(
            """
            UPDATE simulation_experiments
            SET status = 'stopped',
                ended_at = COALESCE(ended_at, now()),
                updated_at = now()
            WHERE id = $1
            RETURNING id, portfolio_id, exchange, symbol, interval, strategy, status,
                      parameters, started_at, ended_at, created_at, updated_at
            """,
            experiment_id,
        )
        return _decode_json_fields(dict(row), "parameters") if row else None

    async def update_simulation_experiment_parameters(
        self,
        experiment_id: int,
        parameters: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        if not self.pool:
            return None
        row = await self.pool.fetchrow(
            """
            UPDATE simulation_experiments
            SET parameters = $2::jsonb,
                updated_at = now()
            WHERE id = $1
            RETURNING id, portfolio_id, exchange, symbol, interval, strategy, status,
                      parameters, started_at, ended_at, created_at, updated_at
            """,
            experiment_id,
            json.dumps(parameters, default=_json_default),
        )
        return _decode_json_fields(dict(row), "parameters") if row else None

    async def stop_running_simulation_experiments(self, *, reason: str = "backend_startup") -> int:
        if not self.pool:
            return 0
        result = await self.pool.execute(
            """
            UPDATE simulation_experiments
            SET status = 'stopped',
                ended_at = COALESCE(ended_at, now()),
                updated_at = now(),
                parameters = jsonb_set(
                  parameters,
                  '{stopped_reason}',
                  to_jsonb($1::text),
                  true
                )
            WHERE status = 'running'
            """,
            reason,
        )
        return int(result.split()[-1])

    async def fetch_simulation_experiments(
        self,
        *,
        portfolio_id: str = "default",
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        if not self.pool:
            return []
        rows = await self.pool.fetch(
            """
            SELECT id, portfolio_id, exchange, symbol, interval, strategy, status,
                   parameters, started_at, ended_at, created_at, updated_at
            FROM simulation_experiments
            WHERE portfolio_id = $1
            ORDER BY started_at DESC
            LIMIT $2
            """,
            portfolio_id,
            limit,
        )
        experiments: list[dict[str, Any]] = []
        for row in rows:
            experiment = _decode_json_fields(dict(row), "parameters")
            pnl = await self.fetch_simulation_pnl(
                portfolio_id=portfolio_id,
                experiment_id=experiment["id"],
            )
            experiment["pnl"] = {
                key: pnl[key]
                for key in (
                    "gross_realized_pnl",
                    "total_fees",
                    "net_realized_pnl",
                    "unrealized_pnl",
                    "equity_pnl",
                    "closed_trade_count",
                    "winning_trade_count",
                    "losing_trade_count",
                    "win_rate_pct",
                    "profit_factor",
                )
            }
            experiment["validation"] = _experiment_validation(experiment["pnl"])
            experiment["scorecard"] = _experiment_scorecard(experiment["pnl"])
            experiments.append(experiment)
        return experiments

    async def fetch_simulation_risk_state(
        self,
        *,
        portfolio_id: str = "default",
        experiment_id: Optional[int] = None,
    ) -> dict[str, Any]:
        if not self.pool:
            return {
                "portfolio_id": portfolio_id,
                "experiment_id": experiment_id,
                "trades_today": 0,
                "fees_today": Decimal("0"),
                "daily_net_pnl": Decimal("0"),
                "consecutive_losses": 0,
            }

        if experiment_id is None:
            order_filter = "portfolio_id = $1"
            fill_filter = "portfolio_id = $1"
            values: tuple[Any, ...] = (portfolio_id,)
        else:
            order_filter = "portfolio_id = $1 AND experiment_id = $2"
            fill_filter = "portfolio_id = $1 AND experiment_id = $2"
            values = (portfolio_id, experiment_id)

        async with self.pool.acquire() as conn:
            trades_today = await conn.fetchval(
                f"""
                SELECT count(*)::int
                FROM simulation_orders
                WHERE {order_filter}
                  AND status = 'filled'
                  AND submitted_at >= date_trunc('day', now())
                """,
                *values,
            )
            fees_today = await conn.fetchval(
                f"""
                SELECT COALESCE(sum(fee), 0)
                FROM simulation_fills
                WHERE {fill_filter}
                  AND created_at >= date_trunc('day', now())
                """,
                *values,
            )

        pnl = await self.fetch_simulation_pnl(
            portfolio_id=portfolio_id,
            experiment_id=experiment_id,
        )
        today = datetime.now(timezone.utc).date()
        daily_net_pnl = Decimal("0")
        consecutive_losses = 0
        for trade in pnl.get("closed_trades", []):
            exit_time = trade.get("exit_time")
            if isinstance(exit_time, str):
                exit_dt = datetime.fromisoformat(exit_time.replace("Z", "+00:00"))
            else:
                exit_dt = exit_time
            if isinstance(exit_dt, datetime) and exit_dt.astimezone(timezone.utc).date() == today:
                daily_net_pnl += Decimal(str(trade.get("net_pnl") or 0))

        for trade in pnl.get("closed_trades", []):
            if Decimal(str(trade.get("net_pnl") or 0)) < 0:
                consecutive_losses += 1
                continue
            break

        return {
            "portfolio_id": portfolio_id,
            "experiment_id": experiment_id,
            "trades_today": int(trades_today or 0),
            "fees_today": Decimal(str(fees_today or 0)),
            "daily_net_pnl": daily_net_pnl,
            "consecutive_losses": consecutive_losses,
        }

    async def fetch_simulation_positions(self, portfolio_id: str = "default") -> list[dict[str, Any]]:
        if not self.pool:
            return []
        rows = await self.pool.fetch(
            """
            SELECT portfolio_id, exchange, symbol, quantity, avg_entry_price,
                   realized_pnl, updated_at
            FROM simulation_positions
            WHERE portfolio_id = $1 AND quantity <> 0
            ORDER BY symbol
            """,
            portfolio_id,
        )
        return [dict(row) for row in rows]

    async def fetch_simulation_portfolio(
        self,
        portfolio_id: str = "default",
        marks: Optional[dict[str, float]] = None,
    ) -> dict[str, Any]:
        if not self.pool:
            return {
                "id": portfolio_id,
                "cash_balance": 0,
                "initial_cash": 0,
                "realized_pnl": 0,
                "unrealized_pnl": 0,
                "equity": 0,
                "positions": [],
            }
        await self._ensure_simulation_portfolio(portfolio_id)
        portfolio = await self.pool.fetchrow(
            """
            SELECT id, cash_balance, initial_cash, realized_pnl, created_at, updated_at
            FROM simulation_portfolios
            WHERE id = $1
            """,
            portfolio_id,
        )
        positions = await self.fetch_simulation_positions(portfolio_id)
        unrealized = Decimal("0")
        gross_market_value = Decimal("0")
        position_rows: list[dict[str, Any]] = []
        for position in positions:
            quantity = Decimal(position["quantity"])
            avg_entry = Decimal(position["avg_entry_price"])
            mark_price = Decimal(str((marks or {}).get(position["symbol"], float(avg_entry))))
            market_value = quantity * mark_price
            unrealized_pnl = (mark_price - avg_entry) * quantity
            unrealized += unrealized_pnl
            gross_market_value += market_value
            enriched = dict(position)
            enriched["mark_price"] = mark_price
            enriched["market_value"] = market_value
            enriched["unrealized_pnl"] = unrealized_pnl
            position_rows.append(enriched)

        cash = Decimal(portfolio["cash_balance"]) if portfolio else Decimal("0")
        realized = Decimal(portfolio["realized_pnl"]) if portfolio else Decimal("0")
        return {
            **dict(portfolio),
            "unrealized_pnl": unrealized,
            "equity": cash + gross_market_value,
            "realized_pnl": realized,
            "positions": position_rows,
        }

    async def fetch_simulation_pnl(
        self,
        portfolio_id: str = "default",
        marks: Optional[dict[str, float]] = None,
        limit: int = 1000,
        experiment_id: Optional[int] = None,
    ) -> dict[str, Any]:
        portfolio = await self.fetch_simulation_portfolio(portfolio_id=portfolio_id, marks=marks)
        fill_source = "portfolio_fills"
        if experiment_id is None:
            source_fills = await self.fetch_simulation_fills_for_pnl(
                portfolio_id=portfolio_id,
                limit=limit,
            )
        else:
            # Use the full portfolio FIFO stream so an experiment exit can be matched
            # against the real entry it closed, even if that entry was not tagged.
            source_fills = await self.fetch_simulation_fills_for_pnl(
                portfolio_id=portfolio_id,
                limit=limit,
            )
            fill_source = "portfolio_fifo_filtered_by_experiment_exit"
        fills = list(
            reversed(source_fills)
        )
        open_qty = Decimal("0")
        avg_entry = Decimal("0")
        entry_fee = Decimal("0")
        entry_time = None
        closed_trades: list[dict[str, Any]] = []
        unmatched_exits: list[dict[str, Any]] = []

        for fill in fills:
            side = fill["side"]
            quantity = Decimal(fill["quantity"])
            price = Decimal(fill["price"])
            fee = Decimal(fill["fee"])
            if side == "buy":
                if open_qty == 0:
                    avg_entry = price
                    entry_fee = fee
                    entry_time = fill["created_at"]
                else:
                    avg_entry = ((avg_entry * open_qty) + (price * quantity)) / (open_qty + quantity)
                    entry_fee += fee
                open_qty += quantity
                continue

            if open_qty <= 0:
                unmatched_exits.append(dict(fill))
                continue

            allocated_entry_fee = entry_fee * (quantity / open_qty) if open_qty else Decimal("0")
            gross_pnl = (price - avg_entry) * quantity
            fees = allocated_entry_fee + fee
            net_pnl = gross_pnl - fees
            basis = (avg_entry * quantity) + allocated_entry_fee
            return_pct = (net_pnl / basis * Decimal("100")) if basis > 0 else None
            trade = {
                "entry_time": entry_time,
                "exit_time": fill["created_at"],
                "symbol": fill["symbol"],
                "quantity": quantity,
                "entry_price": avg_entry,
                "exit_price": price,
                "notional": avg_entry * quantity,
                "gross_pnl": gross_pnl,
                "fees": fees,
                "net_pnl": net_pnl,
                "return_pct": return_pct,
                "entry_experiment_id": None,
                "exit_experiment_id": fill.get("experiment_id"),
            }
            if experiment_id is None or fill.get("experiment_id") == experiment_id:
                closed_trades.append(trade)
            open_qty -= quantity
            if open_qty <= Decimal("0.000000001"):
                open_qty = Decimal("0")
                avg_entry = Decimal("0")
                entry_fee = Decimal("0")
                entry_time = None

        wins = [trade for trade in closed_trades if trade["net_pnl"] > 0]
        losses = [trade for trade in closed_trades if trade["net_pnl"] < 0]
        gross_realized_pnl = sum((trade["gross_pnl"] for trade in closed_trades), Decimal("0"))
        total_fees = sum((trade["fees"] for trade in closed_trades), Decimal("0"))
        net_realized_pnl = sum((trade["net_pnl"] for trade in closed_trades), Decimal("0"))
        gross_profit = sum((trade["net_pnl"] for trade in wins), Decimal("0"))
        gross_loss = abs(sum((trade["net_pnl"] for trade in losses), Decimal("0")))
        equity = Decimal(portfolio["equity"])
        initial_cash = Decimal(portfolio["initial_cash"])
        unrealized_pnl = Decimal(portfolio["unrealized_pnl"])
        return {
            "portfolio_id": portfolio_id,
            "experiment_id": experiment_id,
            "initial_cash": initial_cash,
            "cash_balance": Decimal(portfolio["cash_balance"]),
            "equity": equity,
            "gross_realized_pnl": gross_realized_pnl,
            "total_fees": total_fees,
            "net_realized_pnl": net_realized_pnl,
            "unrealized_pnl": unrealized_pnl,
            "equity_pnl": equity - initial_cash,
            "equity_return_pct": ((equity - initial_cash) / initial_cash * Decimal("100"))
            if initial_cash > 0
            else None,
            "closed_trade_count": len(closed_trades),
            "winning_trade_count": len(wins),
            "losing_trade_count": len(losses),
            "win_rate_pct": (Decimal(len(wins)) / Decimal(len(closed_trades)) * Decimal("100"))
            if closed_trades
            else None,
            "average_win": (gross_profit / Decimal(len(wins))) if wins else None,
            "average_loss": (-gross_loss / Decimal(len(losses))) if losses else None,
            "profit_factor": (gross_profit / gross_loss) if gross_loss > 0 else None,
            "closed_trades": list(reversed(closed_trades[-100:])),
            "unmatched_exit_count": len(unmatched_exits),
            "source": fill_source,
        }

    async def create_simulation_market_order(
        self,
        *,
        experiment_id: Optional[int] = None,
        portfolio_id: str,
        exchange: str,
        symbol: str,
        side: str,
        quantity: Decimal,
        bid_price: Decimal,
        ask_price: Decimal,
        payload: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        if not self.pool:
            return {
                "status": "rejected",
                "rejection_reason": "database unavailable",
            }
        await self._ensure_simulation_portfolio(portfolio_id)
        side = side.lower()
        exchange = exchange.lower()
        symbol = symbol.upper()
        slippage = Decimal(str(settings.simulation_slippage_bps)) / Decimal("10000")
        fee_rate = Decimal(str(settings.simulation_fee_bps)) / Decimal("10000")
        fill_price = ask_price * (Decimal("1") + slippage) if side == "buy" else bid_price * (
            Decimal("1") - slippage
        )
        notional = fill_price * quantity
        fee = notional * fee_rate

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                portfolio = await conn.fetchrow(
                    """
                    SELECT id, cash_balance, initial_cash, realized_pnl
                    FROM simulation_portfolios
                    WHERE id = $1
                    FOR UPDATE
                    """,
                    portfolio_id,
                )
                position = await conn.fetchrow(
                    """
                    SELECT quantity, avg_entry_price, realized_pnl
                    FROM simulation_positions
                    WHERE portfolio_id = $1 AND exchange = $2 AND symbol = $3
                    FOR UPDATE
                    """,
                    portfolio_id,
                    exchange,
                    symbol,
                )
                cash = Decimal(portfolio["cash_balance"])
                old_qty = Decimal(position["quantity"]) if position else Decimal("0")
                old_avg = Decimal(position["avg_entry_price"]) if position else Decimal("0")
                old_realized = Decimal(position["realized_pnl"]) if position else Decimal("0")

                rejection_reason = None
                if quantity <= 0:
                    rejection_reason = "quantity must be positive"
                elif side == "buy" and cash < notional + fee:
                    rejection_reason = "insufficient simulated cash"
                elif side == "sell" and not settings.simulation_allow_short and old_qty < quantity:
                    rejection_reason = "insufficient simulated position"

                order = await conn.fetchrow(
                    """
                    INSERT INTO simulation_orders(
                      experiment_id, portfolio_id, exchange, symbol, side, order_type, status,
                      requested_quantity, filled_quantity, fill_price, fee,
                      filled_at, rejection_reason, payload
                    )
                    VALUES (
                      $1,$2,$3,$4,$5,'market',$6,$7,$8,$9,$10,
                      CASE WHEN $6 = 'filled' THEN now() ELSE NULL END,
                      $11,$12::jsonb
                    )
                    RETURNING id, experiment_id, portfolio_id, exchange, symbol, side, order_type, status,
                              requested_quantity, filled_quantity, fill_price, fee,
                              submitted_at, filled_at, rejection_reason, payload
                    """,
                    experiment_id,
                    portfolio_id,
                    exchange,
                    symbol,
                    side,
                    "rejected" if rejection_reason else "filled",
                    quantity,
                    Decimal("0") if rejection_reason else quantity,
                    None if rejection_reason else fill_price,
                    Decimal("0") if rejection_reason else fee,
                    rejection_reason,
                    json.dumps(payload or {}),
                )
                if rejection_reason:
                    return _decode_json_fields(dict(order), "payload")

                if side == "buy":
                    new_cash = cash - notional - fee
                    new_qty = old_qty + quantity
                    new_avg = ((old_qty * old_avg) + (quantity * fill_price)) / new_qty
                    realized_delta = Decimal("0")
                else:
                    new_cash = cash + notional - fee
                    new_qty = old_qty - quantity
                    new_avg = Decimal("0") if new_qty == 0 else old_avg
                    realized_delta = (fill_price - old_avg) * quantity

                await conn.execute(
                    """
                    INSERT INTO simulation_fills(
                      order_id, experiment_id, portfolio_id, exchange, symbol, side,
                      price, quantity, notional, fee
                    )
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                    """,
                    order["id"],
                    experiment_id,
                    portfolio_id,
                    exchange,
                    symbol,
                    side,
                    fill_price,
                    quantity,
                    notional,
                    fee,
                )
                await conn.execute(
                    """
                    INSERT INTO simulation_positions(
                      portfolio_id, exchange, symbol, quantity, avg_entry_price, realized_pnl
                    )
                    VALUES ($1,$2,$3,$4,$5,$6)
                    ON CONFLICT (portfolio_id, exchange, symbol)
                    DO UPDATE SET
                      quantity = EXCLUDED.quantity,
                      avg_entry_price = EXCLUDED.avg_entry_price,
                      realized_pnl = simulation_positions.realized_pnl + $7,
                      updated_at = now()
                    """,
                    portfolio_id,
                    exchange,
                    symbol,
                    new_qty,
                    new_avg,
                    old_realized + realized_delta,
                    realized_delta,
                )
                await conn.execute(
                    """
                    UPDATE simulation_portfolios
                    SET cash_balance = $2,
                        realized_pnl = realized_pnl + $3,
                        updated_at = now()
                    WHERE id = $1
                    """,
                    portfolio_id,
                    new_cash,
                    realized_delta,
                )
                return _decode_json_fields(dict(order), "payload")

    async def reset_simulation_portfolio(self, portfolio_id: str = "default") -> None:
        if not self.pool:
            return
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("DELETE FROM simulation_equity_snapshots WHERE portfolio_id = $1", portfolio_id)
                await conn.execute("DELETE FROM simulation_strategy_signals WHERE portfolio_id = $1", portfolio_id)
                await conn.execute("DELETE FROM simulation_fills WHERE portfolio_id = $1", portfolio_id)
                await conn.execute("DELETE FROM simulation_orders WHERE portfolio_id = $1", portfolio_id)
                await conn.execute("DELETE FROM simulation_positions WHERE portfolio_id = $1", portfolio_id)
                await conn.execute(
                    """
                    INSERT INTO simulation_portfolios(id, cash_balance, initial_cash, realized_pnl)
                    VALUES ($1,$2,$2,0)
                    ON CONFLICT (id)
                    DO UPDATE SET
                      cash_balance = EXCLUDED.cash_balance,
                      initial_cash = EXCLUDED.initial_cash,
                      realized_pnl = 0,
                      updated_at = now()
                    """,
                    portfolio_id,
                    Decimal(str(settings.simulation_initial_cash)),
                )

    async def _ensure_simulation_portfolio(self, portfolio_id: str = "default") -> None:
        if not self.pool:
            return
        await self.pool.execute(
            """
            INSERT INTO simulation_portfolios(id, cash_balance, initial_cash)
            VALUES ($1,$2,$2)
            ON CONFLICT (id) DO NOTHING
            """,
            portfolio_id,
            Decimal(str(settings.simulation_initial_cash)),
        )

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
            ("trades", "trade_time", settings.trades_retention_days, "day"),
            ("order_book_top", "received_at", settings.order_book_retention_hours, "hour"),
            ("candles", "open_time", settings.candles_retention_days, "day"),
            ("analytics_events", "occurred_at", settings.analytics_events_retention_days, "day"),
            ("analytics_snapshots", "computed_at", settings.analytics_snapshots_retention_days, "day"),
            ("system_events", "occurred_at", settings.system_events_retention_days, "day"),
        ]
        deleted: dict[str, int] = {}
        async with self.pool.acquire() as conn:
            for table_name, timestamp_column, retention_value, retention_unit in cleanup_specs:
                if retention_value <= 0:
                    continue
                result = await conn.execute(
                    f"""
                    DELETE FROM {table_name}
                    WHERE id IN (
                      SELECT id
                      FROM {table_name}
                      WHERE {timestamp_column} < now() - ($1::int * interval '1 {retention_unit}')
                      ORDER BY {timestamp_column}
                      LIMIT $2
                    )
                    """,
                    retention_value,
                    settings.retention_delete_limit,
                )
                deleted[table_name] = int(result.rsplit(" ", 1)[-1])
        return deleted
