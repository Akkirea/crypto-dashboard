from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.simulation.backtest import (
    BacktestConfig,
    required_lookback,
    run_backtest,
    run_momentum_breakout_backtest,
    run_sma_cross_backtest,
    strategy_definitions,
)


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


def test_sma_cross_backtest_produces_read_only_summary_and_trades() -> None:
    closes = [
        Decimal("100"),
        Decimal("99"),
        Decimal("98"),
        Decimal("99"),
        Decimal("101"),
        Decimal("103"),
        Decimal("105"),
        Decimal("104"),
        Decimal("102"),
        Decimal("100"),
    ]
    result = run_sma_cross_backtest(
        [_candle(index, close) for index, close in enumerate(closes)],
        BacktestConfig(
            symbol="AAAUSDT",
            initial_cash=Decimal("10000"),
            short_window=2,
            long_window=3,
            fee_bps=Decimal("0"),
            slippage_bps=Decimal("0"),
        ),
    )

    assert result["read_only"] is True
    assert result["symbol"] == "AAAUSDT"
    assert result["summary"]["trade_count"] >= 1
    assert result["summary"]["final_equity"] > Decimal("0")
    assert result["equity_curve"]
    assert "total_fees" in result["summary"]
    assert "buy_hold_return_pct" in result["summary"]


def test_sma_cross_requires_short_window_below_long_window() -> None:
    try:
        run_sma_cross_backtest(
            [_candle(index, Decimal("100")) for index in range(5)],
            BacktestConfig(symbol="AAAUSDT", short_window=3, long_window=3),
        )
    except ValueError as exc:
        assert "short_window" in str(exc)
    else:
        raise AssertionError("expected invalid window configuration to fail")


def test_strategy_registry_exposes_sma_and_momentum_definitions() -> None:
    definitions = {definition["name"]: definition for definition in strategy_definitions()}

    assert "sma_cross" in definitions
    assert "momentum_breakout" in definitions
    assert definitions["momentum_breakout"]["parameters"]["momentum_window"]["default"] == 20


def test_momentum_breakout_backtest_produces_trades_and_extended_metrics() -> None:
    closes = [
        Decimal("100"),
        Decimal("101"),
        Decimal("102"),
        Decimal("103"),
        Decimal("106"),
        Decimal("108"),
        Decimal("107"),
        Decimal("105"),
        Decimal("104"),
        Decimal("109"),
    ]
    result = run_momentum_breakout_backtest(
        [_candle(index, close) for index, close in enumerate(closes)],
        BacktestConfig(
            symbol="AAAUSDT",
            strategy="momentum_breakout",
            initial_cash=Decimal("10000"),
            momentum_window=3,
            breakout_bps=Decimal("0"),
            exit_window=2,
            fee_bps=Decimal("0"),
            slippage_bps=Decimal("0"),
        ),
    )

    assert result["strategy"] == "momentum_breakout"
    assert result["summary"]["trade_count"] >= 1
    assert result["summary"]["exposure_pct"] is not None
    assert result["summary"]["alpha_vs_buy_hold_pct"] is not None


def test_run_backtest_dispatches_using_registry() -> None:
    result = run_backtest(
        [_candle(index, Decimal(100 + index)) for index in range(10)],
        BacktestConfig(symbol="AAAUSDT", strategy="momentum_breakout", momentum_window=3),
    )

    assert result["strategy"] == "momentum_breakout"
    assert required_lookback(BacktestConfig(symbol="AAAUSDT", strategy="momentum_breakout")) == 20
