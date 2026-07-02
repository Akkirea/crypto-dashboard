from __future__ import annotations

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "local"
    read_only_mode: bool = True
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    database_url: Optional[str] = None
    database_connect_timeout_seconds: int = 10
    database_reconnect_interval_seconds: int = 15
    binance_ws_base: str = "wss://stream.binance.com:9443/stream"
    coinbase_ws_url: str = "wss://ws-feed.exchange.coinbase.com"
    enable_coinbase: bool = True
    kraken_ws_url: str = "wss://ws.kraken.com/v2"
    enable_kraken: bool = False
    bybit_spot_ws_url: str = "wss://stream.bybit.com/v5/public/spot"
    enable_bybit: bool = False
    symbols: str = "BTCUSDT,ETHUSDT,SOLUSDT"
    kline_intervals: str = "1m,5m,15m,1h"
    analytics_interval_seconds: float = 5.0
    spread_widening_alert_ratio: float = 3.0
    volatility_alert_regimes: str = "elevated,extreme"
    trend_alert_abs_score: float = 5.0
    volume_zscore_alert: float = 3.0
    liquidity_collapse_alert_pct: float = 50.0
    simulation_default_exchange: str = "binance"
    simulation_fill_price_source: str = "mid"
    simulation_fee_bps: float = 10.0
    simulation_slippage_bps: float = 1.0
    simulation_latency_ms: int = 250
    simulation_initial_cash: float = 100000.0
    simulation_allow_short: bool = False
    simulation_automation_poll_seconds: float = 15.0
    simulation_automation_default_notional: float = 1000.0
    simulation_automation_max_position_notional: float = 5000.0
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    retention_enabled: bool = True
    retention_initial_delay_seconds: int = 60
    retention_interval_seconds: int = 900
    trades_retention_days: int = 1
    order_book_retention_hours: int = 2
    candles_retention_days: int = 180
    analytics_events_retention_days: int = 30
    analytics_snapshots_retention_days: int = 30
    system_events_retention_days: int = 30
    retention_delete_limit: int = 100000
    order_book_persist_interval_ms: int = 5000
    rollups_enabled: bool = True
    rollup_initial_delay_seconds: int = 45
    rollup_interval_seconds: int = 300
    rollup_lookback_hours: int = 30
    order_book_rollup_bucket_minutes: int = 1

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def symbol_list(self) -> list[str]:
        return [item.strip().upper() for item in self.symbols.split(",") if item.strip()]

    @property
    def interval_list(self) -> list[str]:
        return [item.strip() for item in self.kline_intervals.split(",") if item.strip()]

    @property
    def volatility_alert_regime_list(self) -> set[str]:
        return {
            item.strip().lower()
            for item in self.volatility_alert_regimes.split(",")
            if item.strip()
        }

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


settings = Settings()
