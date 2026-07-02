from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
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
    interval: str = "5m"
    strategy: str = "momentum_breakout"
    enabled: bool = False
    poll_seconds: float = settings.simulation_automation_poll_seconds
    notional: Decimal = Decimal(str(settings.simulation_automation_default_notional))
    max_position_notional: Decimal = Decimal(str(settings.simulation_automation_max_position_notional))
    short_window: int = 5
    long_window: int = 20
    momentum_window: int = 20
    breakout_bps: Decimal = Decimal("25")
    exit_window: int = 10
    min_expected_move_bps: Decimal = Decimal("35")
    min_volume_ratio: Decimal = Decimal("1.20")
    stop_loss_bps: Decimal = Decimal("50")
    trailing_stop_bps: Decimal = Decimal("35")
    take_profit_bps: Decimal = Decimal("100")
    min_holding_minutes: Decimal = Decimal("3")
    max_holding_minutes: Decimal = Decimal("90")
    cooldown_minutes: Decimal = Decimal("5")
    max_spread_bps: Decimal = Decimal("10")
    experiment_id: Optional[int] = None


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
        self._position_state: dict[str, dict[str, Any]] = {}

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
            if config.experiment_id is None:
                experiment = await self.db.create_simulation_experiment(
                    portfolio_id=config.portfolio_id,
                    exchange=config.exchange,
                    symbol=config.symbol,
                    interval=config.interval,
                    strategy=config.strategy,
                    parameters=self._config_payload(config),
                )
                config.experiment_id = experiment["id"] if experiment else None
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
            experiment_id = self.config.experiment_id
            self.config.enabled = False
            self.config.experiment_id = None
        if experiment_id is not None:
            await self.db.end_simulation_experiment(experiment_id)
        await self.db.record_system_event(
            "simulation_automation",
            "stopped",
            status="ok",
            message="automated simulated strategy stopped",
            payload=self.status(),
        )
        return self.status()

    def status(self) -> dict[str, Any]:
        return {
            "read_only": True,
            "live_trading_enabled": False,
            "automated_simulation_enabled": self.config.enabled,
            "config": self._config_payload(self.config),
            "last_signal": self._last_signal,
            "last_error": self._last_error,
        }

    def _config_payload(self, config: AutomationConfig) -> dict[str, Any]:
        payload = asdict(config)
        payload["notional"] = str(config.notional)
        payload["max_position_notional"] = str(config.max_position_notional)
        payload["breakout_bps"] = str(config.breakout_bps)
        payload["min_expected_move_bps"] = str(config.min_expected_move_bps)
        payload["min_volume_ratio"] = str(config.min_volume_ratio)
        payload["stop_loss_bps"] = str(config.stop_loss_bps)
        payload["trailing_stop_bps"] = str(config.trailing_stop_bps)
        payload["take_profit_bps"] = str(config.take_profit_bps)
        payload["min_holding_minutes"] = str(config.min_holding_minutes)
        payload["max_holding_minutes"] = str(config.max_holding_minutes)
        payload["cooldown_minutes"] = str(config.cooldown_minutes)
        payload["max_spread_bps"] = str(config.max_spread_bps)
        return payload

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
        raw_signal, raw_reason, metrics = self._compute_signal(config, candles, position_qty)
        book = await self._book(config.symbol, config.exchange)
        signal, reason, metrics = await self._apply_position_manager(
            config=config,
            raw_signal=raw_signal,
            raw_reason=raw_reason,
            metrics=metrics,
            position=position,
            book=book,
        )
        if signal == "hold":
            return await self._record_signal(
                config,
                signal,
                "observed",
                reason,
                candle["close_time"],
                metrics,
            )

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
            experiment_id=config.experiment_id,
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
                "experiment_id": config.experiment_id,
                "signal_reason": reason,
                "signal_metrics": metrics,
                "read_only": True,
            },
        )
        status = "executed" if order.get("status") == "filled" else "rejected"
        if status == "executed":
            self._update_position_state_after_fill(
                config=config,
                side=side,
                mark_price=(bid_price + ask_price) / Decimal("2"),
            )
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

    def _update_position_state_after_fill(
        self,
        *,
        config: AutomationConfig,
        side: str,
        mark_price: Decimal,
    ) -> None:
        state_key = f"{config.portfolio_id}:{config.exchange}:{config.symbol}"
        state = self._position_state.setdefault(
            state_key,
            {"entry_time": None, "highest_price": None, "last_trade_time": None},
        )
        now = datetime.now(timezone.utc)
        if side == "buy":
            state["entry_time"] = state.get("entry_time") or now
            state["highest_price"] = max(
                Decimal(str(state.get("highest_price") or mark_price)),
                mark_price,
            )
        else:
            state["entry_time"] = None
            state["highest_price"] = None
            state["last_trade_time"] = now

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
        prior_close = Decimal(str(prior[0]["close"]))
        price_change_bps = ((close - prior_close) / prior_close) * Decimal("10000") if prior_close > 0 else Decimal("0")
        recent_volume = Decimal(str(candles[-1].get("volume") or 0))
        average_prior_volume = _mean([Decimal(str(row.get("volume") or 0)) for row in prior])
        volume_ratio = recent_volume / average_prior_volume if average_prior_volume > 0 else Decimal("0")
        exit_rows = candles[-config.exit_window - 1 : -1]
        exit_average = _mean([Decimal(str(row["close"])) for row in exit_rows])
        breakout_level = prior_high * (Decimal("1") + config.breakout_bps / Decimal("10000"))
        round_trip_cost_bps = _estimated_round_trip_cost_bps()
        required_move_bps = max(config.min_expected_move_bps, round_trip_cost_bps + Decimal("10"))
        metrics = {
            "close": str(close),
            "prior_high": str(prior_high),
            "breakout_level": str(breakout_level),
            "exit_average": str(exit_average),
            "price_change_bps": str(price_change_bps),
            "recent_volume": str(recent_volume),
            "average_prior_volume": str(average_prior_volume),
            "volume_ratio": str(volume_ratio),
            "round_trip_cost_bps": str(round_trip_cost_bps),
            "required_move_bps": str(required_move_bps),
        }
        if position_qty <= 0 and close > breakout_level:
            if price_change_bps < required_move_bps:
                return "hold", "expected_move_below_cost_threshold", metrics
            if volume_ratio < config.min_volume_ratio:
                return "hold", "volume_confirmation_failed", metrics
            return "buy", "close_broke_above_prior_high", metrics
        if position_qty > 0 and close < exit_average:
            return "sell", "close_fell_below_exit_average", metrics
        return "hold", "no_momentum_breakout_action", metrics

    async def _apply_position_manager(
        self,
        *,
        config: AutomationConfig,
        raw_signal: str,
        raw_reason: str,
        metrics: dict[str, Any],
        position: Optional[dict[str, Any]],
        book: Optional[dict[str, Any]],
    ) -> tuple[str, str, dict[str, Any]]:
        position_qty = Decimal(str(position["quantity"])) if position else Decimal("0")
        now = datetime.now(timezone.utc)
        mark_price = self._mark_price(position, book, metrics)
        spread_bps = self._spread_bps(book)
        state_key = f"{config.portfolio_id}:{config.exchange}:{config.symbol}"
        state = await self._sync_position_state(config, state_key, position, mark_price)

        manager = {
            "raw_signal": raw_signal,
            "raw_reason": raw_reason,
            "mark_price": str(mark_price) if mark_price is not None else None,
            "spread_bps": str(spread_bps) if spread_bps is not None else None,
            "position_qty": str(position_qty),
            "decision": "hold",
            "reason": raw_reason,
        }

        if spread_bps is not None and spread_bps > config.max_spread_bps:
            manager["market_quality"] = "spread_too_wide"
            metrics["position_manager"] = manager
            if position_qty > 0:
                return "sell", "spread_widened_beyond_limit", metrics
            return "hold", "spread_too_wide_for_entry", metrics

        if position_qty <= 0:
            state["entry_time"] = None
            state["highest_price"] = None
            if raw_signal != "buy":
                metrics["position_manager"] = manager
                return "hold", raw_reason, metrics
            cooldown_remaining = self._cooldown_remaining_minutes(config, state, now)
            if cooldown_remaining > Decimal("0"):
                manager["cooldown_remaining_minutes"] = str(cooldown_remaining)
                metrics["position_manager"] = manager
                return "hold", "trade_cooldown_active", metrics
            manager["decision"] = "buy"
            metrics["position_manager"] = manager
            return "buy", raw_reason, metrics

        if mark_price is None:
            metrics["position_manager"] = manager
            return "hold", "position_manager_missing_mark_price", metrics

        avg_entry = Decimal(str(position["avg_entry_price"]))
        state["highest_price"] = max(Decimal(str(state.get("highest_price") or mark_price)), mark_price)
        entry_time = state.get("entry_time")
        holding_minutes = _elapsed_minutes(entry_time, now) if isinstance(entry_time, datetime) else Decimal("0")
        pnl_bps = ((mark_price - avg_entry) / avg_entry) * Decimal("10000") if avg_entry > 0 else Decimal("0")
        trailing_stop_price = Decimal(str(state["highest_price"])) * (
            Decimal("1") - config.trailing_stop_bps / Decimal("10000")
        )
        edge_score = self._edge_score(raw_signal, pnl_bps, spread_bps, holding_minutes, config)
        risk_score = self._risk_score(pnl_bps, spread_bps, holding_minutes, config)
        manager.update(
            {
                "avg_entry_price": str(avg_entry),
                "unrealized_pnl_bps": str(pnl_bps),
                "highest_price": str(state["highest_price"]),
                "trailing_stop_price": str(trailing_stop_price),
                "holding_minutes": str(holding_minutes),
                "edge_score": str(edge_score),
                "risk_score": str(risk_score),
            }
        )

        if pnl_bps <= -config.stop_loss_bps:
            metrics["position_manager"] = {**manager, "decision": "sell", "exit_type": "hard_stop"}
            return "sell", "stop_loss_triggered", metrics
        if mark_price <= trailing_stop_price:
            metrics["position_manager"] = {**manager, "decision": "sell", "exit_type": "trailing_stop"}
            return "sell", "trailing_stop_triggered", metrics
        if holding_minutes >= config.max_holding_minutes:
            metrics["position_manager"] = {**manager, "decision": "sell", "exit_type": "time_stop"}
            return "sell", "max_holding_time_reached", metrics
        if config.take_profit_bps > 0 and pnl_bps >= config.take_profit_bps and raw_signal != "buy":
            metrics["position_manager"] = {**manager, "decision": "sell", "exit_type": "take_profit"}
            return "sell", "take_profit_reached_after_edge_decay", metrics

        if holding_minutes < config.min_holding_minutes:
            remaining = config.min_holding_minutes - holding_minutes
            manager["min_hold_remaining_minutes"] = str(remaining)
            metrics["position_manager"] = manager
            return "hold", "minimum_hold_active", metrics
        if raw_signal == "sell":
            metrics["position_manager"] = {**manager, "decision": "sell", "exit_type": "strategy_exit"}
            return "sell", raw_reason, metrics

        manager["decision"] = "hold"
        manager["reason"] = "edge_still_valid"
        metrics["position_manager"] = manager
        return "hold", "edge_still_valid_hold_position", metrics

    async def _sync_position_state(
        self,
        config: AutomationConfig,
        state_key: str,
        position: Optional[dict[str, Any]],
        mark_price: Optional[Decimal],
    ) -> dict[str, Any]:
        state = self._position_state.setdefault(
            state_key,
            {"entry_time": None, "highest_price": mark_price, "last_trade_time": None},
        )
        if not position:
            if state.get("entry_time") is not None:
                state["last_trade_time"] = datetime.now(timezone.utc)
            state["entry_time"] = None
            state["highest_price"] = None
            return state
        if state.get("entry_time") is None:
            fills = await self.db.fetch_simulation_fills(portfolio_id=config.portfolio_id, limit=100)
            latest_buy = next(
                (
                    fill
                    for fill in fills
                    if fill["exchange"] == config.exchange
                    and fill["symbol"] == config.symbol
                    and fill["side"] == "buy"
                ),
                None,
            )
            state["entry_time"] = latest_buy["created_at"] if latest_buy else datetime.now(timezone.utc)
            state["highest_price"] = mark_price
        return state

    def _mark_price(
        self,
        position: Optional[dict[str, Any]],
        book: Optional[dict[str, Any]],
        metrics: dict[str, Any],
    ) -> Optional[Decimal]:
        if book is not None:
            bid = Decimal(str(book["bid_price"]))
            ask = Decimal(str(book["ask_price"]))
            return (bid + ask) / Decimal("2")
        if position and position.get("mark_price") is not None:
            return Decimal(str(position["mark_price"]))
        if metrics.get("close") is not None:
            return Decimal(str(metrics["close"]))
        return None

    def _spread_bps(self, book: Optional[dict[str, Any]]) -> Optional[Decimal]:
        if book is None:
            return None
        bid = Decimal(str(book["bid_price"]))
        ask = Decimal(str(book["ask_price"]))
        mid = (bid + ask) / Decimal("2")
        if mid <= 0:
            return None
        return ((ask - bid) / mid) * Decimal("10000")

    def _cooldown_remaining_minutes(
        self,
        config: AutomationConfig,
        state: dict[str, Any],
        now: datetime,
    ) -> Decimal:
        last_trade_time = state.get("last_trade_time")
        if not isinstance(last_trade_time, datetime):
            return Decimal("0")
        elapsed = _elapsed_minutes(last_trade_time, now)
        return max(Decimal("0"), config.cooldown_minutes - elapsed)

    def _edge_score(
        self,
        raw_signal: str,
        pnl_bps: Decimal,
        spread_bps: Optional[Decimal],
        holding_minutes: Decimal,
        config: AutomationConfig,
    ) -> Decimal:
        score = Decimal("0.50")
        if raw_signal == "buy":
            score += Decimal("0.25")
        if raw_signal == "sell":
            score -= Decimal("0.35")
        if pnl_bps > 0:
            score += min(Decimal("0.15"), pnl_bps / Decimal("1000"))
        if spread_bps is not None:
            score -= min(Decimal("0.20"), spread_bps / max(config.max_spread_bps, Decimal("1")) * Decimal("0.10"))
        if holding_minutes >= config.max_holding_minutes * Decimal("0.75"):
            score -= Decimal("0.10")
        return max(Decimal("0"), min(Decimal("1"), score))

    def _risk_score(
        self,
        pnl_bps: Decimal,
        spread_bps: Optional[Decimal],
        holding_minutes: Decimal,
        config: AutomationConfig,
    ) -> Decimal:
        score = Decimal("0")
        if pnl_bps < 0:
            score += min(Decimal("0.45"), abs(pnl_bps) / max(config.stop_loss_bps, Decimal("1")) * Decimal("0.45"))
        if spread_bps is not None:
            score += min(Decimal("0.25"), spread_bps / max(config.max_spread_bps, Decimal("1")) * Decimal("0.25"))
        score += min(Decimal("0.30"), holding_minutes / max(config.max_holding_minutes, Decimal("1")) * Decimal("0.30"))
        return max(Decimal("0"), min(Decimal("1"), score))

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
            experiment_id=config.experiment_id,
        )
        if saved:
            self._last_signal = saved
        return saved


def _mean(values: list[Decimal]) -> Decimal:
    return sum(values, Decimal("0")) / Decimal(len(values))


def _elapsed_minutes(start: datetime, end: datetime) -> Decimal:
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    return Decimal(str(max(0.0, (end - start).total_seconds()) / 60))


def _estimated_round_trip_cost_bps() -> Decimal:
    fee_bps = Decimal(str(settings.simulation_fee_bps))
    slippage_bps = Decimal(str(settings.simulation_slippage_bps))
    return fee_bps * Decimal("2") + slippage_bps * Decimal("2")
