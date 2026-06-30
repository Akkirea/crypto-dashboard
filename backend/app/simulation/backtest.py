from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal


StrategyName = Literal["sma_cross"]


@dataclass(frozen=True)
class BacktestConfig:
    symbol: str
    interval: str = "1m"
    strategy: StrategyName = "sma_cross"
    initial_cash: Decimal = Decimal("10000")
    short_window: int = 5
    long_window: int = 20
    fee_bps: Decimal = Decimal("10")
    slippage_bps: Decimal = Decimal("1")


def run_sma_cross_backtest(
    candles: list[dict[str, Any]],
    config: BacktestConfig,
) -> dict[str, Any]:
    ordered_candles = sorted(candles, key=lambda row: row["open_time"])
    if config.short_window <= 0 or config.long_window <= 0:
        raise ValueError("windows must be positive")
    if config.short_window >= config.long_window:
        raise ValueError("short_window must be lower than long_window")

    cash = config.initial_cash
    quantity = Decimal("0")
    entry_price = Decimal("0")
    realized_pnl = Decimal("0")
    trades: list[dict[str, Any]] = []
    equity_curve: list[dict[str, Any]] = []
    previous_signal = 0
    fee_rate = config.fee_bps / Decimal("10000")
    slippage_rate = config.slippage_bps / Decimal("10000")
    closes: list[Decimal] = []

    for candle in ordered_candles:
        close = Decimal(str(candle["close"]))
        closes.append(close)
        if len(closes) < config.long_window:
            equity_curve.append(_equity_point(candle["close_time"], cash + quantity * close, cash, quantity, close))
            continue

        short_ma = _mean(closes[-config.short_window :])
        long_ma = _mean(closes[-config.long_window :])
        signal = 1 if short_ma > long_ma else 0

        if signal == 1 and previous_signal == 0 and quantity == 0:
            fill_price = close * (Decimal("1") + slippage_rate)
            quantity = cash / (fill_price * (Decimal("1") + fee_rate))
            notional = quantity * fill_price
            fee = notional * fee_rate
            cash -= notional + fee
            entry_price = fill_price
            trades.append(
                _trade(
                    candle["close_time"],
                    "buy",
                    fill_price,
                    quantity,
                    fee,
                    Decimal("0"),
                    "short_ma_crossed_above_long_ma",
                )
            )
        elif signal == 0 and previous_signal == 1 and quantity > 0:
            fill_price = close * (Decimal("1") - slippage_rate)
            notional = quantity * fill_price
            fee = notional * fee_rate
            trade_pnl = (fill_price - entry_price) * quantity - fee
            realized_pnl += trade_pnl
            cash += notional - fee
            trades.append(
                _trade(
                    candle["close_time"],
                    "sell",
                    fill_price,
                    quantity,
                    fee,
                    trade_pnl,
                    "short_ma_crossed_below_long_ma",
                )
            )
            quantity = Decimal("0")
            entry_price = Decimal("0")

        previous_signal = signal
        equity_curve.append(_equity_point(candle["close_time"], cash + quantity * close, cash, quantity, close))

    final_close = Decimal(str(ordered_candles[-1]["close"])) if ordered_candles else Decimal("0")
    final_equity = cash + quantity * final_close
    total_return = _percent_change(config.initial_cash, final_equity)
    max_drawdown = _max_drawdown([Decimal(str(point["equity"])) for point in equity_curve])
    wins = [trade for trade in trades if trade["side"] == "sell" and Decimal(str(trade["realized_pnl"])) > 0]
    closed_trades = [trade for trade in trades if trade["side"] == "sell"]

    return {
        "type": "backtest_result",
        "read_only": True,
        "strategy": config.strategy,
        "symbol": config.symbol,
        "interval": config.interval,
        "parameters": {
            "short_window": config.short_window,
            "long_window": config.long_window,
            "fee_bps": float(config.fee_bps),
            "slippage_bps": float(config.slippage_bps),
            "initial_cash": float(config.initial_cash),
        },
        "sample": {
            "candle_count": len(ordered_candles),
            "start": ordered_candles[0]["open_time"] if ordered_candles else None,
            "end": ordered_candles[-1]["close_time"] if ordered_candles else None,
        },
        "summary": {
            "initial_cash": config.initial_cash,
            "final_equity": final_equity,
            "cash": cash,
            "position_quantity": quantity,
            "position_mark": final_close,
            "realized_pnl": realized_pnl,
            "total_return_pct": total_return,
            "max_drawdown_pct": max_drawdown,
            "trade_count": len(trades),
            "closed_trade_count": len(closed_trades),
            "win_rate_pct": (Decimal(len(wins)) / Decimal(len(closed_trades)) * Decimal("100"))
            if closed_trades
            else None,
        },
        "trades": trades[-100:],
        "equity_curve": equity_curve[-500:],
    }


def _mean(values: list[Decimal]) -> Decimal:
    return sum(values, Decimal("0")) / Decimal(len(values))


def _percent_change(start: Decimal, end: Decimal) -> Decimal | None:
    if start == 0:
        return None
    return (end - start) / start * Decimal("100")


def _max_drawdown(equity_values: list[Decimal]) -> Decimal:
    peak: Decimal | None = None
    worst = Decimal("0")
    for value in equity_values:
        peak = value if peak is None else max(peak, value)
        if peak > 0:
            drawdown = (peak - value) / peak * Decimal("100")
            worst = max(worst, drawdown)
    return worst


def _equity_point(
    timestamp: datetime,
    equity: Decimal,
    cash: Decimal,
    quantity: Decimal,
    mark_price: Decimal,
) -> dict[str, Any]:
    return {
        "time": timestamp,
        "equity": equity,
        "cash": cash,
        "quantity": quantity,
        "mark_price": mark_price,
    }


def _trade(
    timestamp: datetime,
    side: str,
    price: Decimal,
    quantity: Decimal,
    fee: Decimal,
    realized_pnl: Decimal,
    reason: str,
) -> dict[str, Any]:
    return {
        "time": timestamp,
        "side": side,
        "price": price,
        "quantity": quantity,
        "fee": fee,
        "notional": price * quantity,
        "realized_pnl": realized_pnl,
        "reason": reason,
    }
