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
async def test_position_manager_stop_loss_overrides_hold_signal() -> None:
    worker = AutomatedSimulationWorker(MarketState(["AAAUSDT"]), db=None)  # type: ignore[arg-type]
    config = AutomationConfig(
        portfolio_id="default",
        symbol="AAAUSDT",
        stop_loss_bps=Decimal("50"),
        max_spread_bps=Decimal("10"),
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
