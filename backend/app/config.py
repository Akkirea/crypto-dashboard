from __future__ import annotations

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "local"
    read_only_mode: bool = True
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    database_url: Optional[str] = None
    binance_ws_base: str = "wss://stream.binance.com:9443/stream"
    coinbase_ws_url: str = "wss://ws-feed.exchange.coinbase.com"
    enable_coinbase: bool = True
    kraken_ws_url: str = "wss://ws.kraken.com/v2"
    enable_kraken: bool = False
    bybit_spot_ws_url: str = "wss://stream.bybit.com/v5/public/spot"
    enable_bybit: bool = False
    symbols: str = "BTCUSDT,ETHUSDT,SOLUSDT"
    kline_intervals: str = "1m,5m"
    analytics_interval_seconds: float = 5.0
    spread_widening_alert_ratio: float = 3.0
    volatility_alert_regimes: str = "elevated,extreme"
    trend_alert_abs_score: float = 5.0
    volume_zscore_alert: float = 3.0
    liquidity_collapse_alert_pct: float = 50.0

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


settings = Settings()
