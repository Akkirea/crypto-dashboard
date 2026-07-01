from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

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
