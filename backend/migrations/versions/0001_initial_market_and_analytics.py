"""initial market and analytics schema

Revision ID: 0001
Revises:
Create Date: 2026-06-28
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
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


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE IF EXISTS analytics_snapshots;
        DROP TABLE IF EXISTS analytics_events;
        DROP TABLE IF EXISTS ingestion_events;
        DROP TABLE IF EXISTS candles;
        DROP TABLE IF EXISTS order_book_top;
        DROP TABLE IF EXISTS trades;
        DROP TABLE IF EXISTS symbols;
        """
    )
