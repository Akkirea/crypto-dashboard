from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.services.market_state import MarketState
from app.simulation.automation import AutomatedSimulationWorker, AutomationConfig


def _candle(index: int, close: Decimal) -> dict[str, object]:
    open_time = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=index)
    return {
        "open_time": open_time,
        "close_time": open_time + timedelta(seconds=59),
        "open": close,
        "high": close + Decimal("1"),
        "low": close - Decimal("1"),
        "close": close,
        "volume": Decimal("100"),
    }


def _wide_candle(index: int, close: Decimal) -> dict[str, object]:
    candle = _candle(index, close)
    candle["high"] = close + Decimal("4")
    candle["low"] = close - Decimal("4")
    return candle


def test_automation_sma_signal_buys_when_short_ma_above_long_ma() -> None:
    worker = AutomatedSimulationWorker(MarketState(["AAAUSDT"]), db=None)  # type: ignore[arg-type]
    candles = [_candle(index, Decimal(100 + index)) for index in range(20)]

    signal, reason, metrics = worker._compute_signal(
        AutomationConfig(symbol="AAAUSDT", strategy="sma_cross", short_window=3, long_window=8),
        candles,
        Decimal("0"),
    )

    assert signal == "buy"
    assert reason == "short_ma_above_long_ma"
    assert Decimal(metrics["short_ma"]) > Decimal(metrics["long_ma"])


def test_automation_momentum_signal_sells_when_close_breaks_exit_average() -> None:
    worker = AutomatedSimulationWorker(MarketState(["AAAUSDT"]), db=None)  # type: ignore[arg-type]
    closes = [Decimal("100"), Decimal("102"), Decimal("105"), Decimal("106"), Decimal("101")]
    candles = [_candle(index, close) for index, close in enumerate(closes)]

    signal, reason, metrics = worker._compute_signal(
        AutomationConfig(
            symbol="AAAUSDT",
            strategy="momentum_breakout",
            momentum_window=3,
            breakout_bps=Decimal("0"),
            exit_window=2,
        ),
        candles,
        Decimal("1"),
    )

    assert signal == "sell"
    assert reason == "close_fell_below_exit_average"
    assert Decimal(metrics["close"]) < Decimal(metrics["exit_average"])


def test_automation_momentum_entry_requires_expected_move_above_cost() -> None:
    worker = AutomatedSimulationWorker(MarketState(["AAAUSDT"]), db=None)  # type: ignore[arg-type]
    closes = [Decimal("100"), Decimal("100"), Decimal("100"), Decimal("100"), Decimal("100.20")]
    candles = [_candle(index, close) for index, close in enumerate(closes)]
    for candle in candles:
        candle["high"] = candle["close"]

    signal, reason, metrics = worker._compute_signal(
        AutomationConfig(
            symbol="AAAUSDT",
            strategy="momentum_breakout",
            momentum_window=3,
            breakout_bps=Decimal("0"),
            min_expected_move_bps=Decimal("35"),
            min_volume_ratio=Decimal("0"),
        ),
        candles,
        Decimal("0"),
    )

    assert signal == "hold"
    assert reason == "expected_move_below_cost_threshold"
    assert Decimal(metrics["price_change_bps"]) < Decimal(metrics["required_move_bps"])


def test_automation_momentum_entry_requires_trend_filter() -> None:
    worker = AutomatedSimulationWorker(MarketState(["AAAUSDT"]), db=None)  # type: ignore[arg-type]
    closes = [Decimal("110") - Decimal(index) for index in range(55)]
    candles = [_wide_candle(index, close) for index, close in enumerate(closes)]
    candles[-1]["close"] = Decimal("111")
    candles[-1]["high"] = Decimal("112")

    signal, reason, metrics = worker._compute_signal(
        AutomationConfig(
            symbol="AAAUSDT",
            strategy="momentum_breakout",
            momentum_window=3,
            trend_window=20,
            min_trend_bps=Decimal("25"),
            breakout_bps=Decimal("0"),
            min_expected_move_bps=Decimal("0"),
            min_volume_ratio=Decimal("0"),
            min_atr_bps=Decimal("0"),
        ),
        candles,
        Decimal("0"),
    )

    assert signal == "hold"
    assert reason == "trend_filter_failed"
    assert Decimal(metrics["trend_bps"]) < Decimal("25")


def test_automation_momentum_entry_records_dynamic_atr_target() -> None:
    worker = AutomatedSimulationWorker(MarketState(["AAAUSDT"]), db=None)  # type: ignore[arg-type]
    closes = [Decimal("100") + Decimal(index) for index in range(60)]
    candles = [_wide_candle(index, close) for index, close in enumerate(closes)]
    for candle in candles:
        candle["volume"] = Decimal("100")
    candles[-1]["close"] = Decimal("170")
    candles[-1]["high"] = Decimal("171")
    candles[-1]["low"] = Decimal("160")

    signal, reason, metrics = worker._compute_signal(
        AutomationConfig(
            symbol="AAAUSDT",
            strategy="momentum_breakout",
            momentum_window=20,
            trend_window=30,
            breakout_bps=Decimal("0"),
            min_expected_move_bps=Decimal("0"),
            min_volume_ratio=Decimal("0"),
            min_atr_bps=Decimal("0"),
            min_close_location=Decimal("0"),
            min_take_profit_bps=Decimal("50"),
            max_take_profit_bps=Decimal("150"),
            atr_target_multiplier=Decimal("1.2"),
        ),
        candles,
        Decimal("0"),
    )

    assert signal == "buy"
    assert reason == "close_broke_above_prior_high"
    assert Decimal(metrics["dynamic_take_profit_bps"]) >= Decimal("50")


def test_automation_pullback_reclaim_buys_after_recent_low_reclaim() -> None:
    worker = AutomatedSimulationWorker(MarketState(["AAAUSDT"]), db=None)  # type: ignore[arg-type]
    closes = [Decimal("100"), Decimal("102"), Decimal("104"), Decimal("103"), Decimal("101.2")]
    candles = [_candle(index, close) for index, close in enumerate(closes)]
    candles[-1]["open"] = Decimal("100.2")
    candles[-1]["low"] = Decimal("100.8")
    candles[-1]["volume"] = Decimal("150")

    signal, reason, metrics = worker._compute_signal(
        AutomationConfig(
            symbol="AAAUSDT",
            strategy="pullback_reclaim",
            momentum_window=3,
            trend_window=3,
            breakout_bps=Decimal("0"),
            min_trend_bps=Decimal("-100"),
            min_expected_move_bps=Decimal("0"),
            min_volume_ratio=Decimal("0"),
            min_atr_bps=Decimal("0"),
            min_close_location=Decimal("0"),
        ),
        candles,
        Decimal("0"),
    )

    assert signal == "buy"
    assert reason == "pullback_reclaimed_recent_low"
    assert metrics["entry_style"] == "pullback_reclaim"
    assert Decimal(metrics["close"]) > Decimal(metrics["reclaim_level"])


def test_automation_pullback_reclaim_does_not_buy_high_breakout_without_pullback() -> None:
    worker = AutomatedSimulationWorker(MarketState(["AAAUSDT"]), db=None)  # type: ignore[arg-type]
    closes = [Decimal("100"), Decimal("102"), Decimal("104"), Decimal("103"), Decimal("106")]
    candles = [_candle(index, close) for index, close in enumerate(closes)]
    candles[-1]["open"] = Decimal("105")
    candles[-1]["low"] = Decimal("105")

    signal, reason, metrics = worker._compute_signal(
        AutomationConfig(
            symbol="AAAUSDT",
            strategy="pullback_reclaim",
            momentum_window=3,
            trend_window=3,
            breakout_bps=Decimal("0"),
            min_trend_bps=Decimal("-100"),
            min_volume_ratio=Decimal("0"),
            min_atr_bps=Decimal("0"),
            min_close_location=Decimal("0"),
        ),
        candles,
        Decimal("0"),
    )

    assert signal == "hold"
    assert reason == "no_pullback_reclaim_action"
    assert Decimal(metrics["close"]) > Decimal(metrics["target_level"])


def test_automation_pullback_reclaim_requires_cost_adjusted_upside() -> None:
    worker = AutomatedSimulationWorker(MarketState(["AAAUSDT"]), db=None)  # type: ignore[arg-type]
    closes = [Decimal("100"), Decimal("100.2"), Decimal("100.3"), Decimal("100.25"), Decimal("100.12")]
    candles = [_candle(index, close) for index, close in enumerate(closes)]
    for candle in candles[1:4]:
        candle["low"] = Decimal("100.00")
        candle["high"] = Decimal("100.30")
    candles[-1]["open"] = Decimal("100.05")
    candles[-1]["low"] = Decimal("100.00")
    candles[-1]["high"] = Decimal("100.15")
    candles[-1]["volume"] = Decimal("150")

    signal, reason, metrics = worker._compute_signal(
        AutomationConfig(
            symbol="AAAUSDT",
            strategy="pullback_reclaim",
            mode="candidate",
            momentum_window=3,
            trend_window=3,
            breakout_bps=Decimal("0"),
            min_trend_bps=Decimal("-100"),
            min_expected_move_bps=Decimal("0"),
            min_volume_ratio=Decimal("0"),
            min_atr_bps=Decimal("0"),
            min_close_location=Decimal("0"),
            min_reward_to_cost=Decimal("3"),
        ),
        candles,
        Decimal("0"),
    )

    assert signal == "hold"
    assert reason == "expected_move_below_cost_threshold"
    assert Decimal(metrics["expected_move_bps"]) < Decimal(metrics["required_move_bps"])


def test_automation_balanced_mode_uses_two_times_cost_gate() -> None:
    worker = AutomatedSimulationWorker(MarketState(["AAAUSDT"]), db=None)  # type: ignore[arg-type]
    closes = [Decimal("100"), Decimal("100.2"), Decimal("100.3"), Decimal("100.25"), Decimal("100.12")]
    candles = [_candle(index, close) for index, close in enumerate(closes)]
    for candle in candles[1:4]:
        candle["low"] = Decimal("100.00")
        candle["high"] = Decimal("100.80")
    candles[-1]["open"] = Decimal("100.05")
    candles[-1]["low"] = Decimal("100.00")
    candles[-1]["high"] = Decimal("100.15")
    candles[-1]["volume"] = Decimal("150")

    signal, reason, metrics = worker._compute_signal(
        AutomationConfig(
            symbol="AAAUSDT",
            strategy="pullback_reclaim",
            mode="balanced",
            momentum_window=3,
            trend_window=3,
            breakout_bps=Decimal("0"),
            min_trend_bps=Decimal("-100"),
            min_expected_move_bps=Decimal("0"),
            min_volume_ratio=Decimal("0"),
            min_atr_bps=Decimal("0"),
            min_close_location=Decimal("0"),
            min_reward_to_cost=Decimal("2"),
        ),
        candles,
        Decimal("0"),
    )

    assert signal == "buy"
    assert reason == "pullback_reclaimed_recent_low"
    assert Decimal(metrics["required_move_bps"]) == Decimal("44.0")


@pytest.mark.asyncio
async def test_position_manager_blocks_reentry_during_cooldown() -> None:
    worker = AutomatedSimulationWorker(MarketState(["AAAUSDT"]), db=None)  # type: ignore[arg-type]
    config = AutomationConfig(
        portfolio_id="default",
        symbol="AAAUSDT",
        cooldown_minutes=Decimal("5"),
        max_spread_bps=Decimal("10"),
    )
    worker._position_state["default:binance:AAAUSDT"] = {
        "entry_time": None,
        "highest_price": None,
        "last_trade_time": datetime.now(timezone.utc) - timedelta(minutes=1),
    }

    signal, reason, metrics = await worker._apply_position_manager(
        config=config,
        raw_signal="buy",
        raw_reason="close_broke_above_prior_high",
        metrics={"close": "101"},
        position=None,
        book={"bid_price": Decimal("100"), "ask_price": Decimal("100.01")},
    )

    assert signal == "hold"
    assert reason == "trade_cooldown_active"
    assert Decimal(metrics["position_manager"]["cooldown_remaining_minutes"]) > 0


@pytest.mark.asyncio
async def test_position_manager_profit_only_blocks_stop_loss_exit() -> None:
    worker = AutomatedSimulationWorker(MarketState(["AAAUSDT"]), db=None)  # type: ignore[arg-type]
    config = AutomationConfig(
        portfolio_id="default",
        symbol="AAAUSDT",
        stop_loss_bps=Decimal("50"),
        max_spread_bps=Decimal("10"),
        profit_only_exits=True,
    )
    worker._position_state["default:binance:AAAUSDT"] = {
        "entry_time": datetime.now(timezone.utc) - timedelta(minutes=10),
        "highest_price": Decimal("100"),
        "last_trade_time": None,
    }

    signal, reason, metrics = await worker._apply_position_manager(
        config=config,
        raw_signal="hold",
        raw_reason="no_momentum_breakout_action",
        metrics={"close": "99"},
        position={
            "quantity": Decimal("1"),
            "avg_entry_price": Decimal("100"),
            "mark_price": Decimal("99"),
        },
        book={"bid_price": Decimal("98.99"), "ask_price": Decimal("99.01")},
    )

    assert signal == "hold"
    assert reason == "profit_only_exit_blocked_loss_exit"
    assert metrics["position_manager"]["blocked_exit_reason"] == "stop_loss_triggered"
    assert metrics["position_manager"]["profit_only_exits"] is True


@pytest.mark.asyncio
async def test_position_manager_stop_loss_can_be_enabled_for_risk_mode() -> None:
    worker = AutomatedSimulationWorker(MarketState(["AAAUSDT"]), db=None)  # type: ignore[arg-type]
    config = AutomationConfig(
        portfolio_id="default",
        symbol="AAAUSDT",
        stop_loss_bps=Decimal("50"),
        max_spread_bps=Decimal("10"),
        profit_only_exits=False,
    )
    worker._position_state["default:binance:AAAUSDT"] = {
        "entry_time": datetime.now(timezone.utc) - timedelta(minutes=10),
        "highest_price": Decimal("100"),
        "last_trade_time": None,
    }

    signal, reason, metrics = await worker._apply_position_manager(
        config=config,
        raw_signal="hold",
        raw_reason="no_momentum_breakout_action",
        metrics={"close": "99"},
        position={
            "quantity": Decimal("1"),
            "avg_entry_price": Decimal("100"),
            "mark_price": Decimal("99"),
        },
        book={"bid_price": Decimal("98.99"), "ask_price": Decimal("99.01")},
    )

    assert signal == "sell"
    assert reason == "stop_loss_triggered"
    assert metrics["position_manager"]["exit_type"] == "hard_stop"


@pytest.mark.asyncio
async def test_position_manager_take_profit_exits_immediately() -> None:
    worker = AutomatedSimulationWorker(MarketState(["AAAUSDT"]), db=None)  # type: ignore[arg-type]
    config = AutomationConfig(
        portfolio_id="default",
        symbol="AAAUSDT",
        take_profit_bps=Decimal("75"),
        max_holding_minutes=Decimal("60"),
        max_spread_bps=Decimal("10"),
    )
    worker._position_state["default:binance:AAAUSDT"] = {
        "entry_time": datetime.now(timezone.utc) - timedelta(minutes=10),
        "highest_price": Decimal("101"),
        "last_trade_time": None,
    }

    signal, reason, metrics = await worker._apply_position_manager(
        config=config,
        raw_signal="hold",
        raw_reason="no_momentum_breakout_action",
        metrics={"close": "100.80"},
        position={
            "quantity": Decimal("1"),
            "avg_entry_price": Decimal("100"),
            "mark_price": Decimal("100.80"),
        },
        book={"bid_price": Decimal("100.79"), "ask_price": Decimal("100.81")},
    )

    assert signal == "sell"
    assert reason == "take_profit_reached"
    assert metrics["position_manager"]["exit_type"] == "take_profit"
    assert Decimal(metrics["position_manager"]["holding_minutes"]) < config.max_holding_minutes


@pytest.mark.asyncio
async def test_position_manager_records_mae_mfe_and_exits_on_breakout_invalidation() -> None:
    worker = AutomatedSimulationWorker(MarketState(["AAAUSDT"]), db=None)  # type: ignore[arg-type]
    config = AutomationConfig(
        portfolio_id="default",
        symbol="AAAUSDT",
        profit_only_exits=False,
        max_spread_bps=Decimal("10"),
    )
    worker._position_state["default:binance:AAAUSDT"] = {
        "entry_time": datetime.now(timezone.utc) - timedelta(minutes=10),
        "highest_price": Decimal("103"),
        "lowest_price": Decimal("99"),
        "last_trade_time": None,
    }

    signal, reason, metrics = await worker._apply_position_manager(
        config=config,
        raw_signal="hold",
        raw_reason="no_momentum_breakout_action",
        metrics={"close": "99.5", "invalidation_level": "100", "dynamic_take_profit_bps": "75"},
        position={
            "quantity": Decimal("1"),
            "avg_entry_price": Decimal("100"),
            "mark_price": Decimal("99.5"),
        },
        book={"bid_price": Decimal("99.49"), "ask_price": Decimal("99.51")},
    )

    assert signal == "sell"
    assert reason == "breakout_level_lost"
    assert metrics["position_manager"]["exit_type"] == "breakout_invalidation"
    assert Decimal(metrics["position_manager"]["max_favorable_bps"]) > 0
    assert Decimal(metrics["position_manager"]["max_adverse_bps"]) < 0
