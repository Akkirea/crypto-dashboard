"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  ChevronLeft,
  Database,
  LineChart,
  PlaySquare,
  RotateCcw,
  Send,
  ShieldCheck,
  SlidersHorizontal
} from "lucide-react";
import { backendHttpUrl } from "@/lib/backendConfig";
import { fmtPrice, toNumber } from "@/lib/format";
import {
  AutomationSignal,
  AutomationStatus,
  BacktestResult,
  BacktestRunSummary,
  BacktestStrategy,
  SimulationCandle,
  SimulationConfig,
  SimulationFill,
  SimulationInterval,
  SimulationOrder,
  SimulationPnl,
  SimulationPortfolio,
  SimulationSnapshot,
  SimulationTrade
} from "@/lib/simulationTypes";

const STRATEGY_INTERVALS: SimulationInterval[] = ["1m", "5m", "15m", "1h"];

export default function SimulationPage() {
  const [config, setConfig] = useState<SimulationConfig | null>(null);
  const [snapshot, setSnapshot] = useState<SimulationSnapshot | null>(null);
  const [portfolio, setPortfolio] = useState<SimulationPortfolio | null>(null);
  const [pnl, setPnl] = useState<SimulationPnl | null>(null);
  const [orders, setOrders] = useState<SimulationOrder[]>([]);
  const [fills, setFills] = useState<SimulationFill[]>([]);
  const [candles, setCandles] = useState<SimulationCandle[]>([]);
  const [trades, setTrades] = useState<SimulationTrade[]>([]);
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [quantity, setQuantity] = useState("0.001");
  const [backtest, setBacktest] = useState<BacktestResult | null>(null);
  const [backtestRuns, setBacktestRuns] = useState<BacktestRunSummary[]>([]);
  const [automation, setAutomation] = useState<AutomationStatus | null>(null);
  const [automationSignals, setAutomationSignals] = useState<AutomationSignal[]>([]);
  const [strategyInterval, setStrategyInterval] = useState<SimulationInterval>("5m");
  const [backtestStrategy, setBacktestStrategy] = useState<BacktestStrategy>("momentum_breakout");
  const [shortWindow, setShortWindow] = useState("5");
  const [longWindow, setLongWindow] = useState("20");
  const [momentumWindow, setMomentumWindow] = useState("20");
  const [breakoutBps, setBreakoutBps] = useState("10");
  const [exitWindow, setExitWindow] = useState("10");
  const [backtestLimit, setBacktestLimit] = useState("500");
  const [submitting, setSubmitting] = useState(false);
  const [backtesting, setBacktesting] = useState(false);
  const [automationSubmitting, setAutomationSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let closed = false;

    async function loadStatic() {
      try {
        const response = await fetch(`${backendHttpUrl()}/api/simulation/config`, { cache: "no-store" });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = (await response.json()) as SimulationConfig;
        if (!closed) {
          setConfig(data);
          setSymbol(data.symbols[0] ?? "BTCUSDT");
          void loadBacktestRuns();
          void loadAutomation();
        }
      } catch (caught) {
        if (!closed) setError(caught instanceof Error ? caught.message : "simulation config unavailable");
      }
    }

    loadStatic();
    return () => {
      closed = true;
    };
  }, []);

  useEffect(() => {
    let closed = false;

    async function loadMarketData() {
      try {
        const httpUrl = backendHttpUrl();
        const [snapshotResponse, candleResponse, tradeResponse, portfolioResponse, pnlResponse, orderResponse, fillResponse] =
          await Promise.all([
          fetch(`${httpUrl}/api/simulation/market/snapshot`, { cache: "no-store" }),
          fetch(`${httpUrl}/api/simulation/market/candles?symbol=${symbol}&interval=${strategyInterval}&limit=12`, {
            cache: "no-store"
          }),
          fetch(`${httpUrl}/api/simulation/market/trades?symbol=${symbol}&limit=12`, {
            cache: "no-store"
          }),
          fetch(`${httpUrl}/api/simulation/portfolio`, { cache: "no-store" }),
          fetch(`${httpUrl}/api/simulation/pnl`, { cache: "no-store" }),
          fetch(`${httpUrl}/api/simulation/orders?limit=20`, { cache: "no-store" }),
          fetch(`${httpUrl}/api/simulation/fills?limit=20`, { cache: "no-store" })
        ]);
        if (snapshotResponse.ok) {
          const data = (await snapshotResponse.json()) as SimulationSnapshot;
          if (!closed) setSnapshot(data);
        }
        if (candleResponse.ok) {
          const data = (await candleResponse.json()) as SimulationCandle[];
          if (!closed) setCandles(data);
        }
        if (tradeResponse.ok) {
          const data = (await tradeResponse.json()) as SimulationTrade[];
          if (!closed) setTrades(data);
        }
        if (portfolioResponse.ok) {
          const data = (await portfolioResponse.json()) as SimulationPortfolio;
          if (!closed) setPortfolio(data);
        }
        if (pnlResponse.ok) {
          const data = (await pnlResponse.json()) as SimulationPnl;
          if (!closed) setPnl(data);
        }
        if (orderResponse.ok) {
          const data = (await orderResponse.json()) as SimulationOrder[];
          if (!closed) setOrders(data);
        }
        if (fillResponse.ok) {
          const data = (await fillResponse.json()) as SimulationFill[];
          if (!closed) setFills(data);
        }
        if (!closed) setError(null);
      } catch (caught) {
        if (!closed) setError(caught instanceof Error ? caught.message : "simulation data unavailable");
      }
    }

    loadMarketData();
    const interval = window.setInterval(loadMarketData, 5000);
    return () => {
      closed = true;
      window.clearInterval(interval);
    };
  }, [symbol, strategyInterval]);

  useEffect(() => {
    let closed = false;

    async function pollAutomation() {
      if (closed) return;
      await loadAutomation();
    }

    pollAutomation();
    const interval = window.setInterval(pollAutomation, 5000);
    return () => {
      closed = true;
      window.clearInterval(interval);
    };
  }, []);

  const selectedBook = snapshot?.books[symbol];
  const latestCandle = candles.at(-1);
  const latestTrade = trades.at(-1);
  const selectedPosition = portfolio?.positions.find((position) => position.symbol === symbol);
  const totalMessages = useMemo(
    () => Object.values(snapshot?.health.message_counts ?? {}).reduce((sum, value) => sum + value, 0),
    [snapshot]
  );

  async function submitOrder() {
    setSubmitting(true);
    try {
      const response = await fetch(`${backendHttpUrl()}/api/simulation/orders`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol, side, quantity })
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = (await response.json()) as SimulationOrder;
      setOrders((current) => [data, ...current].slice(0, 20));
      const [portfolioResponse, fillResponse] = await Promise.all([
        fetch(`${backendHttpUrl()}/api/simulation/portfolio`, { cache: "no-store" }),
        fetch(`${backendHttpUrl()}/api/simulation/fills?limit=20`, { cache: "no-store" })
      ]);
      if (portfolioResponse.ok) setPortfolio((await portfolioResponse.json()) as SimulationPortfolio);
      if (fillResponse.ok) setFills((await fillResponse.json()) as SimulationFill[]);
      setError(data.status === "rejected" ? data.rejection_reason ?? "order rejected" : null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "order submit failed");
    } finally {
      setSubmitting(false);
    }
  }

  async function resetPortfolio() {
    setSubmitting(true);
    try {
      const response = await fetch(`${backendHttpUrl()}/api/simulation/portfolio/reset`, {
        method: "POST"
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      setPortfolio((await response.json()) as SimulationPortfolio);
      setOrders([]);
      setFills([]);
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "portfolio reset failed");
    } finally {
      setSubmitting(false);
    }
  }

  async function runBacktest() {
    setBacktesting(true);
    try {
      const response = await fetch(`${backendHttpUrl()}/api/simulation/backtests`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol,
          interval: strategyInterval,
          strategy: backtestStrategy,
          short_window: Number(shortWindow),
          long_window: Number(longWindow),
          momentum_window: Number(momentumWindow),
          breakout_bps: Number(breakoutBps),
          exit_window: Number(exitWindow),
          limit: Number(backtestLimit),
          initial_cash: 10000,
          persist: true
        })
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail ?? `HTTP ${response.status}`);
      }
      setBacktest((await response.json()) as BacktestResult);
      await loadBacktestRuns();
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "backtest failed");
    } finally {
      setBacktesting(false);
    }
  }

  async function loadBacktestRuns() {
    const response = await fetch(`${backendHttpUrl()}/api/simulation/backtests/runs?limit=10`, {
      cache: "no-store"
    });
    if (!response.ok) return;
    setBacktestRuns((await response.json()) as BacktestRunSummary[]);
  }

  async function loadBacktestRun(runId: number) {
    setBacktesting(true);
    try {
      const response = await fetch(`${backendHttpUrl()}/api/simulation/backtests/runs/${runId}`, {
        cache: "no-store"
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      setBacktest((await response.json()) as BacktestResult);
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "backtest run unavailable");
    } finally {
      setBacktesting(false);
    }
  }

  async function loadAutomation() {
    try {
      const httpUrl = backendHttpUrl();
      const [statusResponse, signalsResponse] = await Promise.all([
        fetch(`${httpUrl}/api/simulation/automation`, { cache: "no-store" }),
        fetch(`${httpUrl}/api/simulation/automation/signals?limit=20`, { cache: "no-store" })
      ]);
      if (statusResponse.ok) setAutomation((await statusResponse.json()) as AutomationStatus);
      if (signalsResponse.ok) setAutomationSignals((await signalsResponse.json()) as AutomationSignal[]);
    } catch {
      // Market data polling already surfaces broader API failures.
    }
  }

  async function startAutomation() {
    setAutomationSubmitting(true);
    try {
      const response = await fetch(`${backendHttpUrl()}/api/simulation/automation/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol,
          interval: strategyInterval,
          strategy: backtestStrategy,
          poll_seconds: 30,
          notional: 25,
          max_position_notional: 100,
          short_window: Number(shortWindow),
          long_window: Number(longWindow),
          momentum_window: Number(momentumWindow),
          breakout_bps: Number(breakoutBps),
          exit_window: Number(exitWindow),
          min_expected_move_bps: 35,
          min_volume_ratio: 1.2,
          stop_loss_bps: 50,
          trailing_stop_bps: 35,
          take_profit_bps: 100,
          min_holding_minutes: 3,
          max_holding_minutes: 90,
          cooldown_minutes: 5,
          max_spread_bps: 10
        })
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail ?? `HTTP ${response.status}`);
      }
      setAutomation((await response.json()) as AutomationStatus);
      setError(null);
      await loadAutomation();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "automation start failed");
    } finally {
      setAutomationSubmitting(false);
    }
  }

  async function stopAutomation() {
    setAutomationSubmitting(true);
    try {
      const response = await fetch(`${backendHttpUrl()}/api/simulation/automation/stop`, {
        method: "POST"
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      setAutomation((await response.json()) as AutomationStatus);
      setError(null);
      await loadAutomation();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "automation stop failed");
    } finally {
      setAutomationSubmitting(false);
    }
  }

  async function evaluateAutomation() {
    setAutomationSubmitting(true);
    try {
      const response = await fetch(`${backendHttpUrl()}/api/simulation/automation/evaluate`, {
        method: "POST"
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = (await response.json()) as { status: AutomationStatus };
      setAutomation(data.status);
      setError(null);
      await loadAutomation();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "automation evaluate failed");
    } finally {
      setAutomationSubmitting(false);
    }
  }

  return (
    <main className="min-h-screen p-3 text-ink sm:p-5">
      <div className="mx-auto min-h-[calc(100vh-2.5rem)] max-w-[1500px] overflow-hidden rounded-[28px] border border-white/15 bg-black/35 shadow-[0_24px_90px_rgba(0,0,0,0.55)] backdrop-blur-xl">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 p-5">
          <div className="flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-lg bg-gold text-black">
              <PlaySquare className="h-5 w-5" aria-hidden />
            </div>
            <div>
              <h1 className="text-2xl font-semibold text-white">Paper Simulation</h1>
              <div className="mt-1 flex items-center gap-2 text-sm text-muted">
                <ShieldCheck className="h-4 w-4 text-buy" aria-hidden />
                Live simulated execution only
              </div>
            </div>
          </div>
          <Link
            href="/"
            className="inline-flex h-10 items-center gap-2 rounded-lg border border-white/10 bg-white/[0.06] px-3 text-sm text-muted hover:text-white"
          >
            <ChevronLeft className="h-4 w-4" aria-hidden />
            Dashboard
          </Link>
        </header>

        <section className="p-4 sm:p-5 lg:p-6">
          {error ? (
            <section className="mb-4 rounded-lg border border-sell/30 bg-sell/10 p-4 text-sm text-sell">
              Simulation API unavailable: {error}
            </section>
          ) : null}

          <section className="mb-5 grid gap-3 md:grid-cols-4">
            <Metric label="Mode" value={config?.read_only ? "Read-only" : "—"} detail="No execution keys" />
            <Metric label="Feed" value={snapshot?.health.connected ? "Live" : "Pending"} detail={`${totalMessages.toLocaleString()} messages`} />
            <Metric label="Net PnL" value={`$${fmtPrice(toNumber(pnl?.equity_pnl))}`} detail={`${fmtPrice(toNumber(pnl?.equity_return_pct))}% equity`} />
            <Metric label="Fees" value={`$${fmtPrice(toNumber(pnl?.total_fees))}`} detail={`Gross $${fmtPrice(toNumber(pnl?.gross_realized_pnl))}`} />
          </section>

          <section className="mb-5 grid gap-3 md:grid-cols-4">
            <Metric label="Equity" value={`$${fmtPrice(toNumber(pnl?.equity ?? portfolio?.equity))}`} detail={`Cash $${fmtPrice(toNumber(pnl?.cash_balance ?? portfolio?.cash_balance))}`} />
            <Metric label="Closed Trades" value={`${pnl?.closed_trade_count ?? 0}`} detail={`${pnl?.winning_trade_count ?? 0}W / ${pnl?.losing_trade_count ?? 0}L`} />
            <Metric label="Win Rate" value={`${fmtPrice(toNumber(pnl?.win_rate_pct))}%`} detail={`PF ${fmtPrice(toNumber(pnl?.profit_factor))}`} />
            <Metric label="Avg Win/Loss" value={`${fmtPrice(toNumber(pnl?.average_win))} / ${fmtPrice(toNumber(pnl?.average_loss))}`} detail="Net after fees" />
          </section>

          <section className="mb-4 grid gap-4 xl:grid-cols-[320px_minmax(0,1fr)_minmax(340px,0.9fr)]">
            <section className="rounded-lg border border-line bg-panel/90 p-4 shadow-2xl">
              <div className="mb-3 flex items-center gap-2">
                <SlidersHorizontal className="h-4 w-4 text-gold" aria-hidden />
                <h2 className="text-sm font-semibold text-ink">Paper Order</h2>
              </div>
              <div className="mb-4 space-y-3 text-sm">
                <Row label="Price source" value={config?.fill_model.price_source ?? "—"} />
                <Row label="Fee" value={`${config?.fill_model.fee_bps ?? "—"} bps`} />
                <Row label="Slippage" value={`${config?.fill_model.slippage_bps ?? "—"} bps`} />
                <Row label="Latency" value={`${config?.fill_model.latency_ms ?? "—"} ms`} />
                <Row label="Position" value={fmtPrice(toNumber(selectedPosition?.quantity))} />
              </div>
              <div className="mt-5 flex flex-wrap gap-2">
                {(config?.symbols ?? ["BTCUSDT", "ETHUSDT", "SOLUSDT"]).map((item) => (
                  <button
                    key={item}
                    type="button"
                    onClick={() => setSymbol(item)}
                    className={`h-9 rounded-lg border px-3 text-sm ${
                      symbol === item
                        ? "border-gold/50 bg-gold/20 text-white"
                        : "border-white/10 bg-white/[0.05] text-muted hover:text-white"
                    }`}
                  >
                    {item}
                  </button>
                ))}
              </div>
              <div className="mt-4 grid grid-cols-2 gap-2">
                {(["buy", "sell"] as const).map((item) => (
                  <button
                    key={item}
                    type="button"
                    onClick={() => setSide(item)}
                    className={`h-10 rounded-lg border text-sm font-medium capitalize ${
                      side === item
                        ? item === "buy"
                          ? "border-buy/50 bg-buy/20 text-white"
                          : "border-sell/50 bg-sell/20 text-white"
                        : "border-white/10 bg-white/[0.05] text-muted hover:text-white"
                    }`}
                  >
                    {item}
                  </button>
                ))}
              </div>
              <label className="mt-4 block text-xs text-muted">
                Quantity
                <input
                  value={quantity}
                  onChange={(event) => setQuantity(event.target.value)}
                  className="mt-2 h-10 w-full rounded-lg border border-white/10 bg-black/30 px-3 text-sm text-white outline-none focus:border-gold/50"
                  inputMode="decimal"
                />
              </label>
              <button
                type="button"
                onClick={submitOrder}
                disabled={submitting}
                className="mt-4 inline-flex h-10 w-full items-center justify-center gap-2 rounded-lg border border-gold/40 bg-gold/20 text-sm font-medium text-white hover:bg-gold/25 disabled:opacity-50"
              >
                <Send className="h-4 w-4" aria-hidden />
                Submit Simulated Market Order
              </button>
              <button
                type="button"
                onClick={resetPortfolio}
                disabled={submitting}
                className="mt-2 inline-flex h-10 w-full items-center justify-center gap-2 rounded-lg border border-white/10 bg-white/[0.05] text-sm text-muted hover:text-white disabled:opacity-50"
              >
                <RotateCcw className="h-4 w-4" aria-hidden />
                Reset Paper Portfolio
              </button>
            </section>

            <section className="rounded-lg border border-line bg-panel/90 p-4 shadow-2xl">
              <div className="mb-3 flex items-center gap-2">
                <Database className="h-4 w-4 text-accent" aria-hidden />
                <h2 className="text-sm font-semibold text-ink">Recent Candles</h2>
              </div>
              <div className="grid grid-cols-[1fr_1fr_1fr_1fr_1fr] border-b border-line pb-2 text-xs text-muted">
                <span>Time</span>
                <span className="text-right">Open</span>
                <span className="text-right">High</span>
                <span className="text-right">Low</span>
                <span className="text-right">Close</span>
              </div>
              {candles.map((candle) => (
                <div
                  key={`${candle.symbol}-${candle.interval}-${candle.open_time}`}
                  className="grid grid-cols-[1fr_1fr_1fr_1fr_1fr] border-b border-white/[0.06] py-2 text-sm tabular-nums"
                >
                  <span className="text-muted">{new Date(candle.open_time).toLocaleTimeString()}</span>
                  <span className="text-right">{fmtPrice(toNumber(candle.open))}</span>
                  <span className="text-right text-buy">{fmtPrice(toNumber(candle.high))}</span>
                  <span className="text-right text-sell">{fmtPrice(toNumber(candle.low))}</span>
                  <span className="text-right text-white">{fmtPrice(toNumber(candle.close))}</span>
                </div>
              ))}
            </section>

            <section className="rounded-lg border border-line bg-panel/90 p-4 shadow-2xl">
              <div className="mb-3 flex items-center gap-2">
                <Database className="h-4 w-4 text-accent" aria-hidden />
                <h2 className="text-sm font-semibold text-ink">Recent Trades</h2>
              </div>
              <div className="grid grid-cols-[1fr_1fr_1fr] border-b border-line pb-2 text-xs text-muted">
                <span>Time</span>
                <span className="text-right">Price</span>
                <span className="text-right">Qty</span>
              </div>
              {trades.map((trade) => (
                <div
                  key={`${trade.exchange}-${trade.symbol}-${trade.trade_id}`}
                  className="grid grid-cols-[1fr_1fr_1fr] border-b border-white/[0.06] py-2 text-sm tabular-nums"
                >
                  <span className="text-muted">{new Date(trade.trade_time).toLocaleTimeString()}</span>
                  <span className="text-right text-white">{fmtPrice(toNumber(trade.price))}</span>
                  <span className="text-right text-muted">{fmtPrice(toNumber(trade.quantity))}</span>
                </div>
              ))}
            </section>
          </section>

          <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(340px,0.9fr)]">
            <PaperPositions positions={portfolio?.positions ?? []} />
            <PaperOrders orders={orders} />
            <PaperFills fills={fills} />
          </section>

          <AutomationPanel
            status={automation}
            signals={automationSignals}
            running={automationSubmitting}
            onStart={startAutomation}
            onStop={stopAutomation}
            onEvaluate={evaluateAutomation}
          />

          <BacktestPanel
            symbol={symbol}
            interval={strategyInterval}
            strategy={backtestStrategy}
            shortWindow={shortWindow}
            longWindow={longWindow}
            momentumWindow={momentumWindow}
            breakoutBps={breakoutBps}
            exitWindow={exitWindow}
            limit={backtestLimit}
            result={backtest}
            runs={backtestRuns}
            running={backtesting}
            onStrategyChange={setBacktestStrategy}
            onIntervalChange={setStrategyInterval}
            onShortWindowChange={setShortWindow}
            onLongWindowChange={setLongWindow}
            onMomentumWindowChange={setMomentumWindow}
            onBreakoutBpsChange={setBreakoutBps}
            onExitWindowChange={setExitWindow}
            onLimitChange={setBacktestLimit}
            onRun={runBacktest}
            onLoadRun={loadBacktestRun}
          />
        </section>
      </div>
    </main>
  );
}

function PaperPositions({ positions }: { positions: NonNullable<SimulationPortfolio["positions"]> }) {
  return (
    <section className="rounded-lg border border-line bg-panel/90 p-4 shadow-2xl">
      <h2 className="mb-3 text-sm font-semibold text-ink">Positions</h2>
      <div className="grid grid-cols-[1fr_1fr_1fr_1fr] border-b border-line pb-2 text-xs text-muted">
        <span>Symbol</span>
        <span className="text-right">Qty</span>
        <span className="text-right">Avg</span>
        <span className="text-right">UPnL</span>
      </div>
      {positions.length ? (
        positions.map((position) => (
          <div key={position.symbol} className="grid grid-cols-[1fr_1fr_1fr_1fr] border-b border-white/[0.06] py-2 text-sm tabular-nums">
            <span className="font-medium text-white">{position.symbol}</span>
            <span className="text-right">{fmtPrice(toNumber(position.quantity))}</span>
            <span className="text-right">{fmtPrice(toNumber(position.avg_entry_price))}</span>
            <span className="text-right text-buy">{fmtPrice(toNumber(position.unrealized_pnl))}</span>
          </div>
        ))
      ) : (
        <div className="py-4 text-sm text-muted">No simulated positions.</div>
      )}
    </section>
  );
}

function PaperOrders({ orders }: { orders: SimulationOrder[] }) {
  return (
    <section className="rounded-lg border border-line bg-panel/90 p-4 shadow-2xl">
      <h2 className="mb-3 text-sm font-semibold text-ink">Orders</h2>
      <div className="grid grid-cols-[60px_1fr_1fr_1fr] border-b border-line pb-2 text-xs text-muted">
        <span>Side</span>
        <span>Symbol</span>
        <span className="text-right">Status</span>
        <span className="text-right">Fill</span>
      </div>
      {orders.length ? (
        orders.slice(0, 10).map((order) => (
          <div key={order.id} className="grid grid-cols-[60px_1fr_1fr_1fr] border-b border-white/[0.06] py-2 text-sm tabular-nums">
            <span className={order.side === "buy" ? "text-buy" : "text-sell"}>{order.side}</span>
            <span className="font-medium text-white">{order.symbol}</span>
            <span className="text-right text-muted">{order.status}</span>
            <span className="text-right">{fmtPrice(toNumber(order.fill_price))}</span>
          </div>
        ))
      ) : (
        <div className="py-4 text-sm text-muted">No simulated orders.</div>
      )}
    </section>
  );
}

function PaperFills({ fills }: { fills: SimulationFill[] }) {
  return (
    <section className="rounded-lg border border-line bg-panel/90 p-4 shadow-2xl">
      <h2 className="mb-3 text-sm font-semibold text-ink">Fills</h2>
      <div className="grid grid-cols-[60px_1fr_1fr_1fr] border-b border-line pb-2 text-xs text-muted">
        <span>Side</span>
        <span>Symbol</span>
        <span className="text-right">Price</span>
        <span className="text-right">Qty</span>
      </div>
      {fills.length ? (
        fills.slice(0, 10).map((fill) => (
          <div key={fill.id} className="grid grid-cols-[60px_1fr_1fr_1fr] border-b border-white/[0.06] py-2 text-sm tabular-nums">
            <span className={fill.side === "buy" ? "text-buy" : "text-sell"}>{fill.side}</span>
            <span className="font-medium text-white">{fill.symbol}</span>
            <span className="text-right text-white">{fmtPrice(toNumber(fill.price))}</span>
            <span className="text-right text-muted">{fmtPrice(toNumber(fill.quantity))}</span>
          </div>
        ))
      ) : (
        <div className="py-4 text-sm text-muted">No simulated fills.</div>
      )}
    </section>
  );
}

function AutomationPanel({
  status,
  signals,
  running,
  onStart,
  onStop,
  onEvaluate
}: {
  status: AutomationStatus | null;
  signals: AutomationSignal[];
  running: boolean;
  onStart: () => void;
  onStop: () => void;
  onEvaluate: () => void;
}) {
  const enabled = status?.automated_simulation_enabled ?? false;
  const config = status?.config;
  const manager = positionManagerPayload(status?.last_signal);
  const decision = toMetricText(manager?.decision, status?.last_signal?.signal ?? "—");
  const decisionReason = toMetricText(manager?.reason, status?.last_signal?.reason ?? "No decision yet");

  return (
    <section className="mt-5 rounded-lg border border-line bg-panel/90 p-4 shadow-2xl">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <ShieldCheck className={enabled ? "h-4 w-4 text-buy" : "h-4 w-4 text-muted"} aria-hidden />
          <div>
            <h2 className="text-sm font-semibold text-ink">Automated Paper Strategy</h2>
            <p className="mt-1 text-xs text-muted">
              {enabled ? "Running simulated strategy orders" : "Stopped"} · no exchange keys · no real orders
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={onEvaluate}
            disabled={running || !enabled}
            className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-white/10 bg-white/[0.05] px-3 text-sm text-muted hover:text-white disabled:opacity-50"
          >
            Evaluate Once
          </button>
          <button
            type="button"
            onClick={enabled ? onStop : onStart}
            disabled={running}
            className={`inline-flex h-10 items-center justify-center gap-2 rounded-lg border px-4 text-sm font-medium disabled:opacity-50 ${
              enabled
                ? "border-sell/40 bg-sell/15 text-white hover:bg-sell/20"
                : "border-buy/40 bg-buy/15 text-white hover:bg-buy/20"
            }`}
          >
            <PlaySquare className="h-4 w-4" aria-hidden />
            {enabled ? "Stop Automation" : "Start Automation"}
          </button>
        </div>
      </div>

      <section className="mb-4 grid gap-3 md:grid-cols-5">
        <Metric label="Status" value={enabled ? "Running" : "Stopped"} detail={status?.last_error ?? "Read-only simulation"} />
        <Metric label="Strategy" value={config?.strategy ?? "—"} detail={config?.symbol ?? "—"} />
        <Metric label="Notional" value={`$${fmtPrice(toNumber(config?.notional))}`} detail={`Cap $${fmtPrice(toNumber(config?.max_position_notional))}`} />
        <Metric label="Poll" value={`${fmtPrice(toNumber(config?.poll_seconds))}s`} detail={config?.interval ?? "—"} />
        <Metric label="Entry Filter" value={`${fmtPrice(toNumber(config?.min_expected_move_bps))} bps`} detail={`Vol ${fmtPrice(toNumber(config?.min_volume_ratio))}x`} />
      </section>

      <section className="mb-4 grid gap-3 md:grid-cols-5">
        <Metric label="Decision" value={decision} detail={decisionReason} />
        <Metric label="UPnL" value={`${fmtPrice(toMetricNumber(manager?.unrealized_pnl_bps))} bps`} detail={`Risk ${fmtPrice(toMetricNumber(manager?.risk_score))}`} />
        <Metric label="Edge" value={fmtPrice(toMetricNumber(manager?.edge_score))} detail={`Spread ${fmtPrice(toMetricNumber(manager?.spread_bps))} bps`} />
        <Metric label="Trail" value={`$${fmtPrice(toMetricNumber(manager?.trailing_stop_price))}`} detail={`Stop ${fmtPrice(toNumber(config?.stop_loss_bps))} bps`} />
        <Metric
          label="Pacing"
          value={`${fmtPrice(toNumber(config?.cooldown_minutes))}m`}
          detail={`Min ${fmtPrice(toNumber(config?.min_holding_minutes))}m / Max ${fmtPrice(toNumber(config?.max_holding_minutes))}m`}
        />
      </section>

      <section className="overflow-hidden rounded-lg border border-white/[0.08]">
        <div className="grid grid-cols-[80px_1fr_1fr_1fr_1fr] border-b border-line bg-white/[0.03] px-3 py-2 text-xs text-muted">
          <span>Signal</span>
          <span>Strategy</span>
          <span className="text-right">Status</span>
          <span className="text-right">Reason</span>
          <span className="text-right">Time</span>
        </div>
        {signals.map((signal) => (
          <div
            key={signal.id}
            className="grid grid-cols-[80px_1fr_1fr_1fr_1fr] border-b border-white/[0.06] px-3 py-2 text-sm tabular-nums"
          >
            <span className={signal.signal === "buy" ? "text-buy" : signal.signal === "sell" ? "text-sell" : "text-muted"}>
              {signal.signal}
            </span>
            <span className="font-medium text-white">{signal.strategy}</span>
            <span className="text-right text-muted">{signal.status}</span>
            <span className="truncate text-right text-muted">{signal.reason ?? "—"}</span>
            <span className="text-right text-muted">{new Date(signal.created_at).toLocaleTimeString()}</span>
          </div>
        ))}
        {!signals.length ? <div className="px-3 py-4 text-sm text-muted">No automated signals yet.</div> : null}
      </section>
    </section>
  );
}

function positionManagerPayload(signal: AutomationSignal | null | undefined): Record<string, unknown> | null {
  const payload = signal?.payload;
  const value = payload?.position_manager;
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function toMetricNumber(value: unknown) {
  return typeof value === "string" || typeof value === "number" ? toNumber(value) : null;
}

function toMetricText(value: unknown, fallback: string) {
  return typeof value === "string" && value.length > 0 ? value : fallback;
}

function BacktestPanel({
  symbol,
  interval,
  strategy,
  shortWindow,
  longWindow,
  momentumWindow,
  breakoutBps,
  exitWindow,
  limit,
  result,
  runs,
  running,
  onStrategyChange,
  onIntervalChange,
  onShortWindowChange,
  onLongWindowChange,
  onMomentumWindowChange,
  onBreakoutBpsChange,
  onExitWindowChange,
  onLimitChange,
  onRun,
  onLoadRun
}: {
  symbol: string;
  interval: SimulationInterval;
  strategy: BacktestStrategy;
  shortWindow: string;
  longWindow: string;
  momentumWindow: string;
  breakoutBps: string;
  exitWindow: string;
  limit: string;
  result: BacktestResult | null;
  runs: BacktestRunSummary[];
  running: boolean;
  onStrategyChange: (value: BacktestStrategy) => void;
  onIntervalChange: (value: SimulationInterval) => void;
  onShortWindowChange: (value: string) => void;
  onLongWindowChange: (value: string) => void;
  onMomentumWindowChange: (value: string) => void;
  onBreakoutBpsChange: (value: string) => void;
  onExitWindowChange: (value: string) => void;
  onLimitChange: (value: string) => void;
  onRun: () => void;
  onLoadRun: (runId: number) => void;
}) {
  const latestEquity = result?.equity_curve.at(-1);
  const visibleTrades = result?.trades.slice(-8).reverse() ?? [];

  return (
    <section className="mt-5 rounded-lg border border-line bg-panel/90 p-4 shadow-2xl">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <LineChart className="h-4 w-4 text-gold" aria-hidden />
          <div>
            <h2 className="text-sm font-semibold text-ink">Historical Backtest</h2>
            <p className="mt-1 text-xs text-muted">Strategy research on persisted closed candles for {symbol}</p>
          </div>
        </div>
        <button
          type="button"
          onClick={onRun}
          disabled={running}
          className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-gold/40 bg-gold/20 px-4 text-sm font-medium text-white hover:bg-gold/25 disabled:opacity-50"
        >
          <PlaySquare className="h-4 w-4" aria-hidden />
          {running ? "Running" : "Run Backtest"}
        </button>
      </div>

      <div className="mb-4 flex flex-wrap gap-2">
        {STRATEGY_INTERVALS.map((item) => (
          <button
            key={item}
            type="button"
            onClick={() => onIntervalChange(item)}
            className={`h-9 rounded-lg border px-3 text-sm ${
              interval === item
                ? "border-accent/50 bg-accent/20 text-white"
                : "border-white/10 bg-white/[0.05] text-muted hover:text-white"
            }`}
          >
            {item}
          </button>
        ))}
        {([
          ["sma_cross", "SMA Crossover"],
          ["momentum_breakout", "Momentum Breakout"]
        ] as Array<[BacktestStrategy, string]>).map(([item, label]) => (
          <button
            key={item}
            type="button"
            onClick={() => onStrategyChange(item)}
            className={`h-9 rounded-lg border px-3 text-sm ${
              strategy === item
                ? "border-gold/50 bg-gold/20 text-white"
                : "border-white/10 bg-white/[0.05] text-muted hover:text-white"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="mb-4 grid gap-3 md:grid-cols-4">
        {strategy === "sma_cross" ? (
          <>
            <BacktestInput label="Short SMA" value={shortWindow} onChange={onShortWindowChange} />
            <BacktestInput label="Long SMA" value={longWindow} onChange={onLongWindowChange} />
          </>
        ) : (
          <>
            <BacktestInput label="Momentum Window" value={momentumWindow} onChange={onMomentumWindowChange} />
            <BacktestInput label="Breakout bps" value={breakoutBps} onChange={onBreakoutBpsChange} />
            <BacktestInput label="Exit Window" value={exitWindow} onChange={onExitWindowChange} />
          </>
        )}
        <BacktestInput label="Candle Limit" value={limit} onChange={onLimitChange} />
      </div>

      <section className="grid gap-3 md:grid-cols-5">
        <Metric
          label="Return"
          value={`${fmtPrice(toNumber(result?.summary.total_return_pct))}%`}
          detail={`${result?.sample.candle_count ?? 0} candles`}
        />
        <Metric
          label="Equity"
          value={`$${fmtPrice(toNumber(result?.summary.final_equity))}`}
          detail={`Latest $${fmtPrice(toNumber(latestEquity?.mark_price))}`}
        />
        <Metric
          label="Drawdown"
          value={`${fmtPrice(toNumber(result?.summary.max_drawdown_pct))}%`}
          detail="Max peak-to-trough"
        />
        <Metric
          label="Trades"
          value={`${result?.summary.trade_count ?? 0}`}
          detail={`${result?.summary.closed_trade_count ?? 0} closed`}
        />
        <Metric
          label="Win Rate"
          value={`${fmtPrice(toNumber(result?.summary.win_rate_pct))}%`}
          detail="Closed trades"
        />
      </section>

      <section className="mt-3 grid gap-3 md:grid-cols-5">
        <Metric
          label="Fees"
          value={`$${fmtPrice(toNumber(result?.summary.total_fees))}`}
          detail={`Slippage $${fmtPrice(toNumber(result?.summary.total_slippage))}`}
        />
        <Metric
          label="Profit Factor"
          value={fmtPrice(toNumber(result?.summary.profit_factor))}
          detail={`Gross +$${fmtPrice(toNumber(result?.summary.gross_profit))}`}
        />
        <Metric
          label="Avg Win/Loss"
          value={`${fmtPrice(toNumber(result?.summary.average_win))} / ${fmtPrice(toNumber(result?.summary.average_loss))}`}
          detail="Closed trades"
        />
        <Metric
          label="Exposure"
          value={`${fmtPrice(toNumber(result?.summary.exposure_pct))}%`}
          detail="Time in market"
        />
        <Metric
          label="Alpha"
          value={`${fmtPrice(toNumber(result?.summary.alpha_vs_buy_hold_pct))}%`}
          detail={`B&H ${fmtPrice(toNumber(result?.summary.buy_hold_return_pct))}%`}
        />
      </section>

      <section className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(360px,0.8fr)]">
        <section className="overflow-hidden rounded-lg border border-white/[0.08]">
          <div className="grid grid-cols-[1fr_1fr_1fr_1fr] border-b border-line bg-white/[0.03] px-3 py-2 text-xs text-muted">
            <span>Time</span>
            <span className="text-right">Equity</span>
            <span className="text-right">Cash</span>
            <span className="text-right">Position</span>
          </div>
          {(result?.equity_curve.slice(-8).reverse() ?? []).map((point) => (
            <div key={point.time} className="grid grid-cols-[1fr_1fr_1fr_1fr] border-b border-white/[0.06] px-3 py-2 text-sm tabular-nums">
              <span className="text-muted">{new Date(point.time).toLocaleString()}</span>
              <span className="text-right text-white">{fmtPrice(toNumber(point.equity))}</span>
              <span className="text-right">{fmtPrice(toNumber(point.cash))}</span>
              <span className="text-right text-muted">{fmtPrice(toNumber(point.quantity))}</span>
            </div>
          ))}
          {!result ? <div className="px-3 py-4 text-sm text-muted">Run a backtest to see equity history.</div> : null}
        </section>

        <section className="overflow-hidden rounded-lg border border-white/[0.08]">
          <div className="grid grid-cols-[60px_1fr_1fr_1fr] border-b border-line bg-white/[0.03] px-3 py-2 text-xs text-muted">
            <span>Side</span>
            <span className="text-right">Price</span>
            <span className="text-right">Qty</span>
            <span className="text-right">PnL</span>
          </div>
          {visibleTrades.map((trade) => (
            <div key={`${trade.time}-${trade.side}`} className="grid grid-cols-[60px_1fr_1fr_1fr] border-b border-white/[0.06] px-3 py-2 text-sm tabular-nums">
              <span className={trade.side === "buy" ? "text-buy" : "text-sell"}>{trade.side}</span>
              <span className="text-right text-white">{fmtPrice(toNumber(trade.price))}</span>
              <span className="text-right text-muted">{fmtPrice(toNumber(trade.quantity))}</span>
              <span className="text-right">{fmtPrice(toNumber(trade.realized_pnl))}</span>
            </div>
          ))}
          {!visibleTrades.length ? <div className="px-3 py-4 text-sm text-muted">No backtest trades yet.</div> : null}
        </section>
      </section>

      <section className="mt-4 overflow-hidden rounded-lg border border-white/[0.08]">
        <div className="grid grid-cols-[70px_1fr_1fr_1fr_1fr_1fr] border-b border-line bg-white/[0.03] px-3 py-2 text-xs text-muted">
          <span>Run</span>
          <span>Symbol</span>
          <span>Strategy</span>
          <span className="text-right">Return</span>
          <span className="text-right">Trades</span>
          <span className="text-right">Created</span>
        </div>
        {runs.map((run) => (
          <button
            key={run.id}
            type="button"
            onClick={() => onLoadRun(run.id)}
            className="grid w-full grid-cols-[70px_1fr_1fr_1fr_1fr_1fr] border-b border-white/[0.06] px-3 py-2 text-left text-sm tabular-nums hover:bg-white/[0.04]"
          >
            <span className="text-gold">#{run.id}</span>
            <span className="font-medium text-white">{run.symbol}</span>
            <span className="text-muted">{run.strategy}</span>
            <span className="text-right">{fmtPrice(toNumber(run.summary.total_return_pct))}%</span>
            <span className="text-right text-muted">{run.trade_count}</span>
            <span className="text-right text-muted">{new Date(run.created_at).toLocaleTimeString()}</span>
          </button>
        ))}
        {!runs.length ? <div className="px-3 py-4 text-sm text-muted">No saved backtest runs yet.</div> : null}
      </section>
    </section>
  );
}

function BacktestInput({
  label,
  value,
  onChange
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="block text-xs text-muted">
      {label}
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-2 h-10 w-full rounded-lg border border-white/10 bg-black/30 px-3 text-sm text-white outline-none focus:border-gold/50"
        inputMode="numeric"
      />
    </label>
  );
}

function Metric({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <section className="rounded-lg border border-line bg-panel/90 p-4 shadow-2xl">
      <div className="text-xs uppercase text-muted">{label}</div>
      <div className="mt-3 text-xl font-semibold tabular-nums text-white">{value}</div>
      <div className="mt-2 text-xs text-muted">{detail}</div>
    </section>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between border-b border-white/[0.06] pb-2">
      <span className="text-muted">{label}</span>
      <span className="font-medium text-white">{value}</span>
    </div>
  );
}
