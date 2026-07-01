from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable, Literal


StrategyName = Literal["sma_cross", "momentum_breakout"]


@dataclass(frozen=True)
class StrategyDefinition:
    name: StrategyName
    label: str
    description: str
    parameters: dict[str, dict[str, int | float]]
    required_lookback: Callable[["BacktestConfig"], int]
    runner: Callable[[list[dict[str, Any]], "BacktestConfig"], dict[str, Any]]


@dataclass(frozen=True)
class BacktestConfig:
    symbol: str
    interval: str = "1m"
    strategy: StrategyName = "sma_cross"
    initial_cash: Decimal = Decimal("10000")
    short_window: int = 5
    long_window: int = 20
    momentum_window: int = 20
    breakout_bps: Decimal = Decimal("10")
    exit_window: int = 10
    fee_bps: Decimal = Decimal("10")
    slippage_bps: Decimal = Decimal("1")


def run_backtest(candles: list[dict[str, Any]], config: BacktestConfig) -> dict[str, Any]:
    definition = BACKTEST_STRATEGIES.get(config.strategy)
    if definition is None:
        raise ValueError(f"unsupported strategy: {config.strategy}")
    return definition.runner(candles, config)


def run_sma_cross_backtest(
    candles: list[dict[str, Any]],
    config: BacktestConfig,
) -> dict[str, Any]:
    ordered_candles = _ordered_candles(candles)
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
                    _slippage_cost(close, fill_price, quantity, "buy"),
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
                    _slippage_cost(close, fill_price, quantity, "sell"),
                    trade_pnl,
                    "short_ma_crossed_below_long_ma",
                )
            )
            quantity = Decimal("0")
            entry_price = Decimal("0")

        previous_signal = signal
        equity_curve.append(_equity_point(candle["close_time"], cash + quantity * close, cash, quantity, close))

    return _result(ordered_candles, config, cash, quantity, realized_pnl, trades, equity_curve)


def run_momentum_breakout_backtest(
    candles: list[dict[str, Any]],
    config: BacktestConfig,
) -> dict[str, Any]:
    ordered_candles = _ordered_candles(candles)
    if config.momentum_window <= 1 or config.exit_window <= 1:
        raise ValueError("momentum_window and exit_window must be greater than 1")
    if config.breakout_bps < 0:
        raise ValueError("breakout_bps must be non-negative")

    cash = config.initial_cash
    quantity = Decimal("0")
    entry_price = Decimal("0")
    realized_pnl = Decimal("0")
    trades: list[dict[str, Any]] = []
    equity_curve: list[dict[str, Any]] = []
    fee_rate = config.fee_bps / Decimal("10000")
    slippage_rate = config.slippage_bps / Decimal("10000")
    breakout_rate = config.breakout_bps / Decimal("10000")

    for index, candle in enumerate(ordered_candles):
        close = Decimal(str(candle["close"]))
        if index < config.momentum_window:
            equity_curve.append(_equity_point(candle["close_time"], cash + quantity * close, cash, quantity, close))
            continue

        prior_window = ordered_candles[index - config.momentum_window : index]
        prior_high = max(Decimal(str(row["high"])) for row in prior_window)
        exit_start = max(0, index - config.exit_window)
        exit_floor = _mean([Decimal(str(row["close"])) for row in ordered_candles[exit_start:index]])
        breakout_level = prior_high * (Decimal("1") + breakout_rate)

        if quantity == 0 and close > breakout_level:
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
                    _slippage_cost(close, fill_price, quantity, "buy"),
                    Decimal("0"),
                    "close_broke_above_prior_high",
                )
            )
        elif quantity > 0 and close < exit_floor:
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
                    _slippage_cost(close, fill_price, quantity, "sell"),
                    trade_pnl,
                    "close_fell_below_exit_average",
                )
            )
            quantity = Decimal("0")
            entry_price = Decimal("0")

        equity_curve.append(_equity_point(candle["close_time"], cash + quantity * close, cash, quantity, close))

    return _result(ordered_candles, config, cash, quantity, realized_pnl, trades, equity_curve)


def strategy_definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": definition.name,
            "label": definition.label,
            "description": definition.description,
            "parameters": definition.parameters,
        }
        for definition in BACKTEST_STRATEGIES.values()
    ]


def required_lookback(config: BacktestConfig) -> int:
    definition = BACKTEST_STRATEGIES.get(config.strategy)
    if definition is None:
        raise ValueError(f"unsupported strategy: {config.strategy}")
    return definition.required_lookback(config)


def _ordered_candles(candles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(candles, key=lambda row: row["open_time"])


def _result(
    ordered_candles: list[dict[str, Any]],
    config: BacktestConfig,
    cash: Decimal,
    quantity: Decimal,
    realized_pnl: Decimal,
    trades: list[dict[str, Any]],
    equity_curve: list[dict[str, Any]],
) -> dict[str, Any]:
    final_close = Decimal(str(ordered_candles[-1]["close"])) if ordered_candles else Decimal("0")
    final_equity = cash + quantity * final_close
    total_return = _percent_change(config.initial_cash, final_equity)
    buy_hold_return = _buy_hold_return(ordered_candles)
    closed_trades = [trade for trade in trades if trade["side"] == "sell"]
    wins = [trade for trade in closed_trades if Decimal(str(trade["realized_pnl"])) > 0]
    losses = [trade for trade in closed_trades if Decimal(str(trade["realized_pnl"])) < 0]
    gross_profit = sum((Decimal(str(trade["realized_pnl"])) for trade in wins), Decimal("0"))
    gross_loss = abs(sum((Decimal(str(trade["realized_pnl"])) for trade in losses), Decimal("0")))

    return {
        "type": "backtest_result",
        "read_only": True,
        "strategy": config.strategy,
        "symbol": config.symbol,
        "interval": config.interval,
        "parameters": _parameters(config),
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
            "max_drawdown_pct": _max_drawdown([Decimal(str(point["equity"])) for point in equity_curve]),
            "trade_count": len(trades),
            "closed_trade_count": len(closed_trades),
            "win_rate_pct": (Decimal(len(wins)) / Decimal(len(closed_trades)) * Decimal("100"))
            if closed_trades
            else None,
            "total_fees": sum((Decimal(str(trade["fee"])) for trade in trades), Decimal("0")),
            "total_slippage": sum((Decimal(str(trade["slippage"])) for trade in trades), Decimal("0")),
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "average_win": _mean([Decimal(str(trade["realized_pnl"])) for trade in wins]) if wins else None,
            "average_loss": _mean([Decimal(str(trade["realized_pnl"])) for trade in losses]) if losses else None,
            "profit_factor": (gross_profit / gross_loss) if gross_loss > 0 else None,
            "exposure_pct": _exposure_pct(equity_curve),
            "buy_hold_return_pct": buy_hold_return,
            "alpha_vs_buy_hold_pct": total_return - buy_hold_return
            if total_return is not None and buy_hold_return is not None
            else None,
        },
        "trades": trades[-100:],
        "equity_curve": equity_curve[-500:],
    }


def _parameters(config: BacktestConfig) -> dict[str, float | int]:
    parameters: dict[str, float | int] = {
        "fee_bps": float(config.fee_bps),
        "slippage_bps": float(config.slippage_bps),
        "initial_cash": float(config.initial_cash),
    }
    if config.strategy == "momentum_breakout":
        parameters.update(
            {
                "momentum_window": config.momentum_window,
                "breakout_bps": float(config.breakout_bps),
                "exit_window": config.exit_window,
            }
        )
    else:
        parameters.update(
            {
                "short_window": config.short_window,
                "long_window": config.long_window,
            }
        )
    return parameters


def _mean(values: list[Decimal]) -> Decimal:
    return sum(values, Decimal("0")) / Decimal(len(values))


def _percent_change(start: Decimal, end: Decimal) -> Decimal | None:
    if start == 0:
        return None
    return (end - start) / start * Decimal("100")


def _buy_hold_return(candles: list[dict[str, Any]]) -> Decimal | None:
    if len(candles) < 2:
        return None
    first_close = Decimal(str(candles[0]["close"]))
    last_close = Decimal(str(candles[-1]["close"]))
    return _percent_change(first_close, last_close)


def _max_drawdown(equity_values: list[Decimal]) -> Decimal:
    peak: Decimal | None = None
    worst = Decimal("0")
    for value in equity_values:
        peak = value if peak is None else max(peak, value)
        if peak > 0:
            drawdown = (peak - value) / peak * Decimal("100")
            worst = max(worst, drawdown)
    return worst


def _exposure_pct(equity_curve: list[dict[str, Any]]) -> Decimal | None:
    if not equity_curve:
        return None
    exposed = sum(1 for point in equity_curve if Decimal(str(point["quantity"])) != 0)
    return Decimal(exposed) / Decimal(len(equity_curve)) * Decimal("100")


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
    slippage: Decimal,
    realized_pnl: Decimal,
    reason: str,
) -> dict[str, Any]:
    return {
        "time": timestamp,
        "side": side,
        "price": price,
        "quantity": quantity,
        "fee": fee,
        "slippage": slippage,
        "notional": price * quantity,
        "realized_pnl": realized_pnl,
        "reason": reason,
    }


def _slippage_cost(mark_price: Decimal, fill_price: Decimal, quantity: Decimal, side: str) -> Decimal:
    if side == "buy":
        return max(fill_price - mark_price, Decimal("0")) * quantity
    return max(mark_price - fill_price, Decimal("0")) * quantity


BACKTEST_STRATEGIES: dict[StrategyName, StrategyDefinition] = {
    "sma_cross": StrategyDefinition(
        name="sma_cross",
        label="SMA Crossover",
        description=(
            "Long-only candle backtest that buys when the short SMA crosses above "
            "the long SMA and exits on the reverse cross."
        ),
        parameters={
            "short_window": {"default": 5, "min": 2, "max": 200},
            "long_window": {"default": 20, "min": 3, "max": 500},
            "limit": {"default": 500, "min": 50, "max": 2000},
        },
        required_lookback=lambda config: config.long_window,
        runner=run_sma_cross_backtest,
    ),
    "momentum_breakout": StrategyDefinition(
        name="momentum_breakout",
        label="Momentum Breakout",
        description=(
            "Long-only breakout backtest that buys when close breaks above the prior "
            "window high and exits below a short rolling close average."
        ),
        parameters={
            "momentum_window": {"default": 20, "min": 3, "max": 500},
            "breakout_bps": {"default": 10, "min": 0, "max": 1000},
            "exit_window": {"default": 10, "min": 2, "max": 200},
            "limit": {"default": 500, "min": 50, "max": 2000},
        },
        required_lookback=lambda config: max(config.momentum_window, config.exit_window),
        runner=run_momentum_breakout_backtest,
    ),
}
