from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.simulation.backtest import BacktestConfig, run_sma_cross_backtest


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
