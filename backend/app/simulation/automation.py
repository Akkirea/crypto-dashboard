from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from app.config import settings
from app.db.pool import Database
from app.services.market_state import MarketState
from app.simulation.backtest import BacktestConfig, required_lookback

logger = logging.getLogger(__name__)


@dataclass
class AutomationConfig:
    portfolio_id: str = "default"
    exchange: str = "binance"
    symbol: str = "BTCUSDT"
    interval: str = "1m"
    strategy: str = "momentum_breakout"
    enabled: bool = False
    poll_seconds: float = settings.simulation_automation_poll_seconds
    notional: Decimal = Decimal(str(settings.simulation_automation_default_notional))
    max_position_notional: Decimal = Decimal(str(settings.simulation_automation_max_position_notional))
    short_window: int = 5
    long_window: int = 20
    momentum_window: int = 20
    breakout_bps: Decimal = Decimal("10")
    exit_window: int = 10


class AutomatedSimulationWorker:
    def __init__(self, state: MarketState, db: Database) -> None:
        self.state = state
        self.db = db
        self.config = AutomationConfig(symbol=state.symbols[0] if state.symbols else "BTCUSDT")
        self._lock = asyncio.Lock()
        self._stop = asyncio.Event()
        self._last_candle_key: Optional[str] = None
        self._last_signal: Optional[dict[str, Any]] = None
        self._last_error: Optional[str] = None

    async def run(self) -> None:
        while not self._stop.is_set():
            try:
                if self.config.enabled:
                    await self.evaluate_once()
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=max(1.0, float(self.config.poll_seconds)),
                )
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._last_error = str(exc)
                logger.exception("automated simulation worker failed")
                await asyncio.sleep(max(1.0, float(self.config.poll_seconds)))

    async def stop(self) -> None:
        self._stop.set()

    async def start_strategy(self, config: AutomationConfig) -> dict[str, Any]:
        async with self._lock:
            if config.symbol not in self.state.symbols:
                raise ValueError(f"unsupported symbol: {config.symbol}")
            if config.strategy not in {"sma_cross", "momentum_breakout"}:
                raise ValueError(f"unsupported strategy: {config.strategy}")
            if config.notional <= 0:
                raise ValueError("notional must be positive")
            if config.max_position_notional <= 0:
                raise ValueError("max_position_notional must be positive")
            if config.strategy == "sma_cross" and config.short_window >= config.long_window:
                raise ValueError("short_window must be lower than long_window")
            config.enabled = True
            self.config = config
            self._last_candle_key = None
            self._last_error = None
        await self.db.record_system_event(
            "simulation_automation",
            "started",
            status="ok",
            message="automated simulated strategy started",
            payload=self.status(),
        )
        return self.status()

    async def stop_strategy(self) -> dict[str, Any]:
        async with self._lock:
            self.config.enabled = False
        await self.db.record_system_event(
            "simulation_automation",
            "stopped",
            status="ok",
            message="automated simulated strategy stopped",
            payload=self.status(),
        )
        return self.status()

    def status(self) -> dict[str, Any]:
        payload = asdict(self.config)
        payload["notional"] = str(self.config.notional)
        payload["max_position_notional"] = str(self.config.max_position_notional)
        payload["breakout_bps"] = str(self.config.breakout_bps)
        return {
            "read_only": True,
            "live_trading_enabled": False,
            "automated_simulation_enabled": self.config.enabled,
            "config": payload,
            "last_signal": self._last_signal,
            "last_error": self._last_error,
        }

    async def evaluate_once(self) -> Optional[dict[str, Any]]:
        async with self._lock:
            config = AutomationConfig(**asdict(self.config))
        if not config.enabled:
            return None

        backtest_config = BacktestConfig(
            symbol=config.symbol,
            interval=config.interval,
            strategy=config.strategy,
            short_window=config.short_window,
            long_window=config.long_window,
            momentum_window=config.momentum_window,
            breakout_bps=config.breakout_bps,
            exit_window=config.exit_window,
        )
        lookback = required_lookback(backtest_config)
        candles = await self.db.fetch_backtest_candles(
            config.symbol,
            config.interval,
            exchange=config.exchange,
            limit=max(lookback + 5, 50),
        )
        if len(candles) < lookback + 1:
            return await self._record_signal(
                config,
                "hold",
                "skipped",
                f"not enough closed candles: have {len(candles)}, need {lookback + 1}",
                None,
                {"candle_count": len(candles)},
            )

        candle = candles[-1]
        candle_key = str(candle["close_time"])
        if candle_key == self._last_candle_key:
            return None
        self._last_candle_key = candle_key

        portfolio = await self.db.fetch_simulation_portfolio(
            portfolio_id=config.portfolio_id,
            marks=self.state.latest_prices,
        )
        position = next(
            (item for item in portfolio["positions"] if item["symbol"] == config.symbol),
            None,
        )
        position_qty = Decimal(str(position["quantity"])) if position else Decimal("0")
        signal, reason, metrics = self._compute_signal(config, candles, position_qty)
        if signal == "hold":
            return await self._record_signal(
                config,
                signal,
                "observed",
                reason,
                candle["close_time"],
                metrics,
            )

        book = await self._book(config.symbol, config.exchange)
        if book is None:
            return await self._record_signal(
                config,
                signal,
                "skipped",
                "no book available for simulated fill",
                candle["close_time"],
                metrics,
            )

        bid_price = Decimal(str(book["bid_price"]))
        ask_price = Decimal(str(book["ask_price"]))
        side = "buy" if signal == "buy" else "sell"
        if side == "buy":
            mid = (bid_price + ask_price) / Decimal("2")
            current_notional = position_qty * mid
            available_notional = min(config.notional, config.max_position_notional - current_notional)
            if available_notional <= 0:
                return await self._record_signal(
                    config,
                    signal,
                    "skipped",
                    "max simulated position notional reached",
                    candle["close_time"],
                    {**metrics, "current_notional": str(current_notional)},
                )
            quantity = available_notional / ask_price
        else:
            if position_qty <= 0:
                return await self._record_signal(
                    config,
                    signal,
                    "skipped",
                    "no simulated position to sell",
                    candle["close_time"],
                    metrics,
                )
            quantity = position_qty

        order = await self.db.create_simulation_market_order(
            portfolio_id=config.portfolio_id,
            exchange=config.exchange,
            symbol=config.symbol,
            side=side,
            quantity=quantity,
            bid_price=bid_price,
            ask_price=ask_price,
            payload={
                "source": "automated_simulation",
                "strategy": config.strategy,
                "signal_reason": reason,
                "signal_metrics": metrics,
                "read_only": True,
            },
        )
        status = "executed" if order.get("status") == "filled" else "rejected"
        saved_signal = await self._record_signal(
            config,
            signal,
            status,
            order.get("rejection_reason") or reason,
            candle["close_time"],
            {**metrics, "order": order},
            order_id=order.get("id"),
        )
        return saved_signal

    def _compute_signal(
        self,
        config: AutomationConfig,
        candles: list[dict[str, Any]],
        position_qty: Decimal,
    ) -> tuple[str, str, dict[str, Any]]:
        if config.strategy == "sma_cross":
            closes = [Decimal(str(row["close"])) for row in candles]
            short_ma = _mean(closes[-config.short_window:])
            long_ma = _mean(closes[-config.long_window:])
            metrics = {"short_ma": str(short_ma), "long_ma": str(long_ma)}
            if position_qty <= 0 and short_ma > long_ma:
                return "buy", "short_ma_above_long_ma", metrics
            if position_qty > 0 and short_ma <= long_ma:
                return "sell", "short_ma_below_or_equal_long_ma", metrics
            return "hold", "no_sma_cross_action", metrics

        close = Decimal(str(candles[-1]["close"]))
        prior = candles[-config.momentum_window - 1 : -1]
        prior_high = max(Decimal(str(row["high"])) for row in prior)
        exit_rows = candles[-config.exit_window - 1 : -1]
        exit_average = _mean([Decimal(str(row["close"])) for row in exit_rows])
        breakout_level = prior_high * (Decimal("1") + config.breakout_bps / Decimal("10000"))
        metrics = {
            "close": str(close),
            "prior_high": str(prior_high),
            "breakout_level": str(breakout_level),
            "exit_average": str(exit_average),
        }
        if position_qty <= 0 and close > breakout_level:
            return "buy", "close_broke_above_prior_high", metrics
        if position_qty > 0 and close < exit_average:
            return "sell", "close_fell_below_exit_average", metrics
        return "hold", "no_momentum_breakout_action", metrics

    async def _book(self, symbol: str, exchange: str) -> Optional[dict[str, Any]]:
        book = self.state.books.get(symbol)
        if book is not None:
            return {
                "bid_price": book.bid_price,
                "ask_price": book.ask_price,
            }
        return await self.db.fetch_latest_book_top(symbol, exchange=exchange)

    async def _record_signal(
        self,
        config: AutomationConfig,
        signal: str,
        status: str,
        reason: str,
        candle_time: Optional[datetime],
        payload: dict[str, Any],
        order_id: Optional[int] = None,
    ) -> Optional[dict[str, Any]]:
        saved = await self.db.save_strategy_signal(
            portfolio_id=config.portfolio_id,
            exchange=config.exchange,
            symbol=config.symbol,
            strategy=config.strategy,
            signal=signal,
            status=status,
            reason=reason,
            candle_time=candle_time,
            order_id=order_id,
            payload=payload,
        )
        if saved:
            self._last_signal = saved
        return saved


def _mean(values: list[Decimal]) -> Decimal:
    return sum(values, Decimal("0")) / Decimal(len(values))
