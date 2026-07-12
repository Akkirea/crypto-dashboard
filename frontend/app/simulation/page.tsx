"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
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
  SimulationExperiment,
  SimulationFill,
  SimulationInterval,
  SimulationOrder,
  SimulationPnl,
  SimulationPortfolio,
  SimulationSnapshot,
  SimulationTrade
} from "@/lib/simulationTypes";

const STRATEGY_INTERVALS: SimulationInterval[] = ["1m", "5m", "15m", "1h"];
type AutomationMode = "exploration" | "candidate";

const AUTOMATION_PRESETS: Record<
  AutomationMode,
  {
    label: string;
    description: string;
    target: string;
    payload: {
      interval: SimulationInterval;
      poll_seconds: number;
      notional: number;
      max_position_notional: number;
      momentum_window: number;
      breakout_bps: number;
      exit_window: number;
      trend_window: number;
      min_trend_bps: number;
      atr_window: number;
      atr_target_multiplier: number;
      min_take_profit_bps: number;
      max_take_profit_bps: number;
      min_close_location: number;
      min_atr_bps: number;
      min_expected_move_bps: number;
      min_volume_ratio: number;
      stop_loss_bps: number;
      trailing_stop_bps: number;
      take_profit_bps: number;
      min_holding_minutes: number;
      max_holding_minutes: number;
      cooldown_minutes: number;
      max_spread_bps: number;
      daily_max_loss: number;
      max_trades_per_day: number;
      max_fee_burn_per_day: number;
      pause_after_loss_streak: number;
      profit_only_exits: boolean;
      min_reward_to_cost: number;
    };
  }
> = {
  exploration: {
    label: "Exploration",
    description: "Higher-frequency 5m data collection with tiny simulated size.",
    target: "15-40 trades/day",
    payload: {
      interval: "5m",
      poll_seconds: 30,
      notional: 10,
      max_position_notional: 50,
      momentum_window: 6,
      breakout_bps: 5,
      exit_window: 4,
      trend_window: 12,
      min_trend_bps: -25,
      atr_window: 10,
      atr_target_multiplier: 1.0,
      min_take_profit_bps: 35,
      max_take_profit_bps: 90,
      min_close_location: 0.45,
      min_atr_bps: 3,
      min_expected_move_bps: 18,
      min_volume_ratio: 0.55,
      stop_loss_bps: 65,
      trailing_stop_bps: 45,
      take_profit_bps: 55,
      min_holding_minutes: 5,
      max_holding_minutes: 45,
      cooldown_minutes: 0,
      max_spread_bps: 10,
      daily_max_loss: 20,
      max_trades_per_day: 40,
      max_fee_burn_per_day: 8,
      pause_after_loss_streak: 6,
      profit_only_exits: false,
      min_reward_to_cost: 1.5
    }
  },
  candidate: {
    label: "Candidate",
    description: "Stricter 15m forward validation for signals that survive costs.",
    target: "1-8 trades/day",
    payload: {
      interval: "15m",
      poll_seconds: 60,
      notional: 25,
      max_position_notional: 100,
      momentum_window: 20,
      breakout_bps: 25,
      exit_window: 10,
      trend_window: 50,
      min_trend_bps: 0,
      atr_window: 14,
      atr_target_multiplier: 1.2,
      min_take_profit_bps: 50,
      max_take_profit_bps: 150,
      min_close_location: 0.65,
      min_atr_bps: 10,
      min_expected_move_bps: 45,
      min_volume_ratio: 1.5,
      stop_loss_bps: 75,
      trailing_stop_bps: 50,
      take_profit_bps: 90,
      min_holding_minutes: 30,
      max_holding_minutes: 240,
      cooldown_minutes: 10,
      max_spread_bps: 10,
      daily_max_loss: 25,
      max_trades_per_day: 8,
      max_fee_burn_per_day: 5,
      pause_after_loss_streak: 3,
      profit_only_exits: false,
      min_reward_to_cost: 3
    }
  }
};

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
  const [orderType, setOrderType] = useState<"market" | "limit">("market");
  const [quantity, setQuantity] = useState("0.001");
  const [limitPrice, setLimitPrice] = useState("");
  const [backtest, setBacktest] = useState<BacktestResult | null>(null);
  const [backtestRuns, setBacktestRuns] = useState<BacktestRunSummary[]>([]);
  const [experiments, setExperiments] = useState<SimulationExperiment[]>([]);
  const [automation, setAutomation] = useState<AutomationStatus | null>(null);
  const [automationSignals, setAutomationSignals] = useState<AutomationSignal[]>([]);
  const [automationMode, setAutomationMode] = useState<AutomationMode>("candidate");
  const [strategyInterval, setStrategyInterval] = useState<SimulationInterval>("5m");
  const [backtestStrategy, setBacktestStrategy] = useState<BacktestStrategy>("pullback_reclaim");
  const [shortWindow, setShortWindow] = useState("5");
  const [longWindow, setLongWindow] = useState("20");
  const [momentumWindow, setMomentumWindow] = useState("20");
  const [breakoutBps, setBreakoutBps] = useState("25");
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
        const [snapshotResponse, candleResponse, tradeResponse, portfolioResponse, pnlResponse, experimentResponse, orderResponse, fillResponse] =
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
          fetch(`${httpUrl}/api/simulation/experiments?limit=10`, { cache: "no-store" }),
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
        if (experimentResponse.ok) {
          const data = (await experimentResponse.json()) as SimulationExperiment[];
          if (!closed) setExperiments(data);
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

  const selectedPosition = portfolio?.positions.find((position) => position.symbol === symbol);
  const totalMessages = useMemo(
    () => Object.values(snapshot?.health.message_counts ?? {}).reduce((sum, value) => sum + value, 0),
    [snapshot]
  );
  const currentExperiment = useMemo(
    () => experiments.find((experiment) => experiment.id === automation?.config.experiment_id) ?? experiments.find((experiment) => experiment.status === "running") ?? experiments[0] ?? null,
    [automation?.config.experiment_id, experiments]
  );
  const currentExperimentId = currentExperiment?.id ?? automation?.config.experiment_id ?? null;
  const currentOrders = currentExperimentId === null ? orders : orders.filter((order) => order.experiment_id === currentExperimentId);
  const currentFills = currentExperimentId === null ? fills : fills.filter((fill) => fill.experiment_id === currentExperimentId);
  const latestSignal = automation?.last_signal ?? null;
  const latestManager = positionManagerPayload(latestSignal);
  const activeAutomationMode = automation?.config.mode ?? automationMode;

  async function submitOrder() {
    setSubmitting(true);
    try {
      const response = await fetch(`${backendHttpUrl()}/api/simulation/orders`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol,
          side,
          quantity,
          order_type: orderType,
          ...(orderType === "limit" ? { limit_price: limitPrice } : {})
        })
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
      const preset = AUTOMATION_PRESETS[automationMode];
      const response = await fetch(`${backendHttpUrl()}/api/simulation/automation/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol,
          mode: automationMode,
          interval: preset.payload.interval,
          strategy: backtestStrategy,
          poll_seconds: preset.payload.poll_seconds,
          notional: preset.payload.notional,
          max_position_notional: preset.payload.max_position_notional,
          short_window: Number(shortWindow),
          long_window: Number(longWindow),
          momentum_window: preset.payload.momentum_window,
          breakout_bps: preset.payload.breakout_bps,
          exit_window: preset.payload.exit_window,
          trend_window: preset.payload.trend_window,
          min_trend_bps: preset.payload.min_trend_bps,
          atr_window: preset.payload.atr_window,
          atr_target_multiplier: preset.payload.atr_target_multiplier,
          min_take_profit_bps: preset.payload.min_take_profit_bps,
          max_take_profit_bps: preset.payload.max_take_profit_bps,
          min_close_location: preset.payload.min_close_location,
          min_atr_bps: preset.payload.min_atr_bps,
          min_expected_move_bps: preset.payload.min_expected_move_bps,
          min_volume_ratio: preset.payload.min_volume_ratio,
          stop_loss_bps: preset.payload.stop_loss_bps,
          trailing_stop_bps: preset.payload.trailing_stop_bps,
          take_profit_bps: preset.payload.take_profit_bps,
          min_holding_minutes: preset.payload.min_holding_minutes,
          max_holding_minutes: preset.payload.max_holding_minutes,
          cooldown_minutes: preset.payload.cooldown_minutes,
          max_spread_bps: preset.payload.max_spread_bps,
          daily_max_loss: preset.payload.daily_max_loss,
          max_trades_per_day: preset.payload.max_trades_per_day,
          max_fee_burn_per_day: preset.payload.max_fee_burn_per_day,
          pause_after_loss_streak: preset.payload.pause_after_loss_streak,
          profit_only_exits: preset.payload.profit_only_exits,
          min_reward_to_cost: preset.payload.min_reward_to_cost
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
    <main className="min-h-screen p-2 text-ink sm:p-5">
      <div className="mx-auto min-h-[calc(100vh-1rem)] max-w-[1500px] overflow-hidden rounded-2xl border border-white/15 bg-black/35 shadow-[0_24px_90px_rgba(0,0,0,0.55)] backdrop-blur-xl sm:min-h-[calc(100vh-2.5rem)] sm:rounded-[28px]">
        <header className="flex flex-col items-start justify-between gap-3 border-b border-white/10 p-4 sm:flex-row sm:items-center sm:p-5">
          <div className="flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-lg bg-gold text-black">
              <PlaySquare className="h-5 w-5" aria-hidden />
            </div>
            <div>
              <h1 className="text-xl font-semibold text-white sm:text-2xl">Paper Simulation</h1>
              <div className="mt-1 flex items-center gap-2 text-sm text-muted">
                <ShieldCheck className="h-4 w-4 text-buy" aria-hidden />
                Live simulated execution only
              </div>
            </div>
          </div>
          <Link
            href="/"
            className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-lg border border-white/10 bg-white/[0.06] px-3 text-sm text-muted hover:text-white sm:w-auto"
          >
            <ChevronLeft className="h-4 w-4" aria-hidden />
            Dashboard
          </Link>
        </header>

        <section className="p-3 sm:p-5 lg:p-6">
          {error ? (
            <section className="mb-4 rounded-lg border border-sell/30 bg-sell/10 p-4 text-sm text-sell">
              Simulation API unavailable: {error}
            </section>
          ) : null}

          <MonitorPanel
            automation={automation}
            experiment={currentExperiment}
            pnl={pnl}
            position={selectedPosition}
            latestSignal={latestSignal}
            latestManager={latestManager}
            feedConnected={snapshot?.health.connected ?? false}
            messageCount={totalMessages}
          />

          <AutomationPanel
            status={automation}
            signals={automationSignals}
            selectedMode={automationMode}
            activeMode={activeAutomationMode}
            running={automationSubmitting}
            onModeChange={setAutomationMode}
            onStart={startAutomation}
            onStop={stopAutomation}
            onEvaluate={evaluateAutomation}
          />

          <section className="mt-5 grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(360px,0.8fr)]">
            <ExperimentPanel experiments={experiments} />
            <section className="grid gap-4">
              <PaperOrders orders={currentOrders} title="Current Experiment Orders" />
              <PaperFills fills={currentFills} title="Current Experiment Fills" />
            </section>
          </section>

          <CollapsibleSection title="Manual Paper Order" defaultOpen={false}>
            <ManualOrderPanel
              config={config}
              symbols={config?.symbols ?? ["BTCUSDT", "ETHUSDT", "SOLUSDT"]}
              symbol={symbol}
              side={side}
              orderType={orderType}
              quantity={quantity}
              limitPrice={limitPrice}
              positionQuantity={fmtPrice(toNumber(selectedPosition?.quantity))}
              submitting={submitting}
              onSymbolChange={setSymbol}
              onSideChange={setSide}
              onOrderTypeChange={setOrderType}
              onQuantityChange={setQuantity}
              onLimitPriceChange={setLimitPrice}
              onSubmit={submitOrder}
              onReset={resetPortfolio}
            />
          </CollapsibleSection>

          <CollapsibleSection title="Research Backtests" defaultOpen={false}>
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
          </CollapsibleSection>

          <CollapsibleSection title="Market Data Debug" defaultOpen={false}>
            <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
              <MarketCandles candles={candles} />
              <MarketTrades trades={trades} />
            </section>
            <section className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(340px,0.9fr)]">
              <PaperPositions positions={portfolio?.positions ?? []} />
              <PaperOrders orders={orders} title="All Orders" />
              <PaperFills fills={fills} title="All Fills" />
            </section>
          </CollapsibleSection>
        </section>
      </div>
    </main>
  );
}

function MonitorPanel({
  automation,
  experiment,
  pnl,
  position,
  latestSignal,
  latestManager,
  feedConnected,
  messageCount
}: {
  automation: AutomationStatus | null;
  experiment: SimulationExperiment | null;
  pnl: SimulationPnl | null;
  position: SimulationPortfolio["positions"][number] | undefined;
  latestSignal: AutomationSignal | null;
  latestManager: Record<string, unknown> | null;
  feedConnected: boolean;
  messageCount: number;
}) {
  const running = automation?.automated_simulation_enabled ?? false;
  const decision = toMetricText(latestManager?.decision, latestSignal?.signal ?? "—");
  const reason = toMetricText(latestManager?.reason, latestSignal?.reason ?? "No signal yet");
  const pnlValue = toNumber(experiment?.pnl.net_realized_pnl);
  const pnlClass = pnlValue === null ? "text-white" : pnlValue >= 0 ? "text-buy" : "text-sell";

  return (
    <section className="rounded-lg border border-line bg-panel/90 p-4 shadow-2xl">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <ShieldCheck className={running ? "h-4 w-4 text-buy" : "h-4 w-4 text-muted"} aria-hidden />
            <h2 className="text-sm font-semibold text-ink">Live Simulation Monitor</h2>
          </div>
          <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted">
            <span className={running ? "text-buy" : "text-muted"}>{running ? "Running" : "Stopped"}</span>
            <span>Experiment #{experiment?.id ?? "—"}</span>
            <span>{automation?.config.strategy ?? "—"}</span>
            <span>{automation?.config.mode ?? "—"}</span>
            <span>{automation?.config.interval ?? "—"}</span>
          </div>
        </div>
        <div className="rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-right text-xs text-muted">
          <div className={feedConnected ? "text-buy" : "text-sell"}>{feedConnected ? "Feed live" : "Feed pending"}</div>
          <div className="mt-1">{messageCount.toLocaleString()} messages</div>
        </div>
      </div>

      <section className="grid gap-3 md:grid-cols-4">
        <Metric label="Current PnL" value={`$${fmtPrice(pnlValue)}`} detail={`${experiment?.pnl.closed_trade_count ?? 0} closed trades`} valueClassName={pnlClass} />
        <Metric label="Decision" value={decision} detail={reason} />
        <Metric label="Position" value={fmtPrice(toNumber(position?.quantity))} detail={`UPnL $${fmtPrice(toNumber(position?.unrealized_pnl))}`} />
        <Metric label="Account PnL" value={`$${fmtPrice(toNumber(pnl?.equity_pnl))}`} detail={`Blended history · PF ${fmtPrice(toNumber(pnl?.profit_factor))}`} />
      </section>

      <section className="mt-3 grid gap-3 md:grid-cols-4">
        <Metric label="Expectancy" value={`$${fmtPrice(toNumber(experiment?.scorecard?.expectancy_per_trade))}`} detail={`${experiment?.pnl.winning_trade_count ?? 0}W / ${experiment?.pnl.losing_trade_count ?? 0}L`} />
        <Metric label="Profit Factor" value={fmtPrice(toNumber(experiment?.pnl.profit_factor))} detail={`${fmtPrice(toNumber(experiment?.scorecard?.fee_drag_pct))}% fee drag`} />
        <Metric label="Cost Gate" value={`${fmtPrice(toNumber(automation?.config.min_reward_to_cost))}x`} detail={`Move ${fmtPrice(toNumber(automation?.config.min_expected_move_bps))} bps · Vol ${fmtPrice(toNumber(automation?.config.min_volume_ratio))}x`} />
        <Metric label="Risk Mode" value={automation?.config.profit_only_exits ? "Profit-only" : "Invalidation"} detail={`${automation?.config.max_trades_per_day ?? "—"} trades/day`} />
      </section>
    </section>
  );
}

function ManualOrderPanel({
  config,
  symbols,
  symbol,
  side,
  orderType,
  quantity,
  limitPrice,
  positionQuantity,
  submitting,
  onSymbolChange,
  onSideChange,
  onOrderTypeChange,
  onQuantityChange,
  onLimitPriceChange,
  onSubmit,
  onReset
}: {
  config: SimulationConfig | null;
  symbols: string[];
  symbol: string;
  side: "buy" | "sell";
  orderType: "market" | "limit";
  quantity: string;
  limitPrice: string;
  positionQuantity: string;
  submitting: boolean;
  onSymbolChange: (value: string) => void;
  onSideChange: (value: "buy" | "sell") => void;
  onOrderTypeChange: (value: "market" | "limit") => void;
  onQuantityChange: (value: string) => void;
  onLimitPriceChange: (value: string) => void;
  onSubmit: () => void;
  onReset: () => void;
}) {
  const takerFee = config?.fill_model.taker_fee_bps ?? config?.fill_model.fee_bps ?? "—";
  const makerFee = config?.fill_model.maker_fee_bps ?? "—";

  return (
    <section className="grid gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
      <section className="rounded-lg border border-line bg-panel/90 p-4">
        <div className="mb-3 flex items-center gap-2">
          <SlidersHorizontal className="h-4 w-4 text-gold" aria-hidden />
          <h2 className="text-sm font-semibold text-ink">Paper Order Ticket</h2>
        </div>
        <div className="mb-4 space-y-3 text-sm">
          <Row label="Price source" value={config?.fill_model.price_source ?? "—"} />
          <Row label="Taker fee" value={`${takerFee} bps`} />
          <Row label="Maker fee" value={`${makerFee} bps`} />
          <Row label="Slippage" value={`${config?.fill_model.slippage_bps ?? "—"} bps`} />
          <Row label="Latency" value={`${config?.fill_model.latency_ms ?? "—"} ms`} />
          <Row label="Position" value={positionQuantity} />
        </div>
        <div className="flex flex-wrap gap-2">
          {symbols.map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => onSymbolChange(item)}
              className={`h-9 rounded-lg border px-3 text-sm ${
                symbol === item ? "border-gold/50 bg-gold/20 text-white" : "border-white/10 bg-white/[0.05] text-muted hover:text-white"
              }`}
            >
              {item}
            </button>
          ))}
        </div>
      </section>

      <section className="rounded-lg border border-line bg-panel/90 p-4">
        <div className="mb-3 grid grid-cols-2 gap-2">
          {(["market", "limit"] as const).map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => onOrderTypeChange(item)}
              className={`h-10 rounded-lg border text-sm font-medium capitalize ${
                orderType === item
                  ? "border-gold/50 bg-gold/20 text-white"
                  : "border-white/10 bg-white/[0.05] text-muted hover:text-white"
              }`}
            >
              {item}
            </button>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-2">
          {(["buy", "sell"] as const).map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => onSideChange(item)}
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
            onChange={(event) => onQuantityChange(event.target.value)}
            className="mt-2 h-10 w-full rounded-lg border border-white/10 bg-black/30 px-3 text-sm text-white outline-none focus:border-gold/50"
            inputMode="decimal"
          />
        </label>
        {orderType === "limit" ? (
          <label className="mt-4 block text-xs text-muted">
            Limit price
            <input
              value={limitPrice}
              onChange={(event) => onLimitPriceChange(event.target.value)}
              className="mt-2 h-10 w-full rounded-lg border border-white/10 bg-black/30 px-3 text-sm text-white outline-none focus:border-gold/50"
              inputMode="decimal"
              placeholder="e.g. 64000"
            />
          </label>
        ) : null}
        <div className="mt-4 grid gap-2 sm:grid-cols-2">
          <button
            type="button"
            onClick={onSubmit}
            disabled={submitting}
            className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-gold/40 bg-gold/20 px-3 text-sm font-medium text-white hover:bg-gold/25 disabled:opacity-50"
          >
            <Send className="h-4 w-4" aria-hidden />
            Submit
          </button>
          <button
            type="button"
            onClick={onReset}
            disabled={submitting}
            className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-white/10 bg-white/[0.05] px-3 text-sm text-muted hover:text-white disabled:opacity-50"
          >
            <RotateCcw className="h-4 w-4" aria-hidden />
            Reset
          </button>
        </div>
      </section>
    </section>
  );
}

function MarketCandles({ candles }: { candles: SimulationCandle[] }) {
  return (
    <section className="rounded-lg border border-line bg-panel/90 p-4">
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
        <div key={`${candle.symbol}-${candle.interval}-${candle.open_time}`} className="grid grid-cols-[1fr_1fr_1fr_1fr_1fr] border-b border-white/[0.06] py-2 text-sm tabular-nums">
          <span className="text-muted">{new Date(candle.open_time).toLocaleTimeString()}</span>
          <span className="text-right">{fmtPrice(toNumber(candle.open))}</span>
          <span className="text-right text-buy">{fmtPrice(toNumber(candle.high))}</span>
          <span className="text-right text-sell">{fmtPrice(toNumber(candle.low))}</span>
          <span className="text-right text-white">{fmtPrice(toNumber(candle.close))}</span>
        </div>
      ))}
    </section>
  );
}

function MarketTrades({ trades }: { trades: SimulationTrade[] }) {
  return (
    <section className="rounded-lg border border-line bg-panel/90 p-4">
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
        <div key={`${trade.exchange}-${trade.symbol}-${trade.trade_id}`} className="grid grid-cols-[1fr_1fr_1fr] border-b border-white/[0.06] py-2 text-sm tabular-nums">
          <span className="text-muted">{new Date(trade.trade_time).toLocaleTimeString()}</span>
          <span className="text-right text-white">{fmtPrice(toNumber(trade.price))}</span>
          <span className="text-right text-muted">{fmtPrice(toNumber(trade.quantity))}</span>
        </div>
      ))}
    </section>
  );
}

function PaperPositions({ positions }: { positions: NonNullable<SimulationPortfolio["positions"]> }) {
  return (
    <section className="rounded-lg border border-line bg-panel/90 p-4 shadow-2xl">
      <h2 className="mb-3 text-sm font-semibold text-ink">Positions</h2>
      <div className="hidden grid-cols-[1fr_1fr_1fr_1fr] border-b border-line pb-2 text-xs text-muted sm:grid">
        <span>Symbol</span>
        <span className="text-right">Qty</span>
        <span className="text-right">Avg</span>
        <span className="text-right">UPnL</span>
      </div>
      {positions.length ? (
        positions.map((position) => (
          <div key={position.symbol} className="border-b border-white/[0.06] py-3 text-sm tabular-nums sm:grid sm:grid-cols-[1fr_1fr_1fr_1fr] sm:py-2">
            <div className="mb-2 font-medium text-white sm:mb-0">{position.symbol}</div>
            <MobileField label="Qty" value={fmtPrice(toNumber(position.quantity))} />
            <MobileField label="Avg" value={fmtPrice(toNumber(position.avg_entry_price))} />
            <MobileField label="UPnL" value={fmtPrice(toNumber(position.unrealized_pnl))} valueClassName="text-buy" />
          </div>
        ))
      ) : (
        <div className="py-4 text-sm text-muted">No simulated positions.</div>
      )}
    </section>
  );
}

function PaperOrders({ orders, title = "Orders" }: { orders: SimulationOrder[]; title?: string }) {
  return (
    <section className="rounded-lg border border-line bg-panel/90 p-4 shadow-2xl">
      <h2 className="mb-3 text-sm font-semibold text-ink">{title}</h2>
      <div className="hidden grid-cols-[60px_1fr_1fr_1fr] border-b border-line pb-2 text-xs text-muted sm:grid">
        <span>Side</span>
        <span>Symbol</span>
        <span className="text-right">Status</span>
        <span className="text-right">Price</span>
      </div>
      {orders.length ? (
        orders.slice(0, 10).map((order) => (
          <div key={order.id} className="border-b border-white/[0.06] py-3 text-sm tabular-nums sm:grid sm:grid-cols-[60px_1fr_1fr_1fr] sm:py-2">
            <div className="mb-2 flex items-center justify-between sm:mb-0 sm:block">
              <span className={order.side === "buy" ? "text-buy" : "text-sell"}>{order.side}</span>
              <span className="font-medium text-white sm:hidden">{order.symbol}</span>
            </div>
            <span className="hidden font-medium text-white sm:block">
              {order.symbol}
              <span className="ml-2 text-xs font-normal text-muted">{order.order_type}</span>
            </span>
            <MobileField label="Status" value={order.status} valueClassName="text-muted" />
            <MobileField
              label={order.status === "submitted" ? "Limit" : "Fill"}
              value={fmtPrice(toNumber(order.fill_price ?? order.limit_price))}
            />
          </div>
        ))
      ) : (
        <div className="py-4 text-sm text-muted">No simulated orders.</div>
      )}
    </section>
  );
}

function PaperFills({ fills, title = "Fills" }: { fills: SimulationFill[]; title?: string }) {
  return (
    <section className="rounded-lg border border-line bg-panel/90 p-4 shadow-2xl">
      <h2 className="mb-3 text-sm font-semibold text-ink">{title}</h2>
      <div className="hidden grid-cols-[60px_1fr_1fr_1fr] border-b border-line pb-2 text-xs text-muted sm:grid">
        <span>Side</span>
        <span>Symbol</span>
        <span className="text-right">Price</span>
        <span className="text-right">Qty</span>
      </div>
      {fills.length ? (
        fills.slice(0, 10).map((fill) => (
          <div key={fill.id} className="border-b border-white/[0.06] py-3 text-sm tabular-nums sm:grid sm:grid-cols-[60px_1fr_1fr_1fr] sm:py-2">
            <div className="mb-2 flex items-center justify-between sm:mb-0 sm:block">
              <span className={fill.side === "buy" ? "text-buy" : "text-sell"}>{fill.side}</span>
              <span className="font-medium text-white sm:hidden">{fill.symbol}</span>
            </div>
            <span className="hidden font-medium text-white sm:block">{fill.symbol}</span>
            <MobileField label="Price" value={fmtPrice(toNumber(fill.price))} valueClassName="text-white" />
            <MobileField label="Qty" value={fmtPrice(toNumber(fill.quantity))} valueClassName="text-muted" />
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
  selectedMode,
  activeMode,
  running,
  onModeChange,
  onStart,
  onStop,
  onEvaluate
}: {
  status: AutomationStatus | null;
  signals: AutomationSignal[];
  selectedMode: AutomationMode;
  activeMode: AutomationMode;
  running: boolean;
  onModeChange: (mode: AutomationMode) => void;
  onStart: () => void;
  onStop: () => void;
  onEvaluate: () => void;
}) {
  const enabled = status?.automated_simulation_enabled ?? false;
  const config = status?.config;
  const manager = positionManagerPayload(status?.last_signal);
  const latestPayload = status?.last_signal?.payload;
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

      <section className="mb-4 grid gap-3 md:grid-cols-2">
        {(Object.keys(AUTOMATION_PRESETS) as AutomationMode[]).map((mode) => {
          const preset = AUTOMATION_PRESETS[mode];
          const selected = selectedMode === mode;
          const active = enabled && activeMode === mode;
          return (
            <button
              key={mode}
              type="button"
              onClick={() => onModeChange(mode)}
              disabled={running || enabled}
              className={`rounded-lg border p-4 text-left transition disabled:cursor-not-allowed ${
                selected
                  ? "border-gold/50 bg-gold/15"
                  : "border-white/10 bg-white/[0.04] hover:border-white/25 hover:bg-white/[0.06]"
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="font-medium text-white">{preset.label}</div>
                  <div className="mt-1 text-xs text-muted">{preset.description}</div>
                </div>
                <div className={`rounded-md px-2 py-1 text-xs ${active ? "bg-buy/15 text-buy" : "bg-white/[0.06] text-muted"}`}>
                  {active ? "active" : preset.payload.interval}
                </div>
              </div>
              <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
                <div className="rounded-md bg-black/20 p-2">
                  <div className="text-muted">Target</div>
                  <div className="mt-1 text-white">{preset.target}</div>
                </div>
                <div className="rounded-md bg-black/20 p-2">
                  <div className="text-muted">Notional</div>
                  <div className="mt-1 text-white">${preset.payload.notional}</div>
                </div>
                <div className="rounded-md bg-black/20 p-2">
                  <div className="text-muted">Max/day</div>
                  <div className="mt-1 text-white">{preset.payload.max_trades_per_day}</div>
                </div>
                <div className="rounded-md bg-black/20 p-2">
                  <div className="text-muted">Cost gate</div>
                  <div className="mt-1 text-white">{preset.payload.min_reward_to_cost}x</div>
                </div>
              </div>
            </button>
          );
        })}
      </section>

      <section className="mb-4 grid gap-3 md:grid-cols-5">
        <Metric label="Status" value={enabled ? "Running" : "Stopped"} detail={status?.last_error ?? "Read-only simulation"} />
        <Metric label="Strategy" value={config?.strategy ?? "—"} detail={`${config?.mode ?? selectedMode} · ${config?.symbol ?? "—"}`} />
        <Metric label="Notional" value={`$${fmtPrice(toNumber(config?.notional))}`} detail={`Cap $${fmtPrice(toNumber(config?.max_position_notional))}`} />
        <Metric label="Poll" value={`${fmtPrice(toNumber(config?.poll_seconds))}s`} detail={config?.interval ?? "—"} />
        <Metric label="Cost Gate" value={`${fmtPrice(toNumber(config?.min_reward_to_cost))}x`} detail={`Move ${fmtPrice(toNumber(config?.min_expected_move_bps))} bps · Close ${fmtPrice(toNumber(config?.min_close_location))}`} />
      </section>

      <section className="mb-4 grid gap-3 md:grid-cols-5">
        <Metric label="Decision" value={decision} detail={decisionReason} />
        <Metric label="UPnL" value={`${fmtPrice(toMetricNumber(manager?.unrealized_pnl_bps))} bps`} detail={`MAE ${fmtPrice(toMetricNumber(manager?.max_adverse_bps))} / MFE ${fmtPrice(toMetricNumber(manager?.max_favorable_bps))}`} />
        <Metric label="Edge" value={fmtPrice(toMetricNumber(manager?.edge_score))} detail={`Spread ${fmtPrice(toMetricNumber(manager?.spread_bps))} bps`} />
        <Metric label="Target" value={`${fmtPrice(toMetricNumber(manager?.target_bps ?? latestPayload?.dynamic_take_profit_bps))} bps`} detail={`ATR ${fmtPrice(toMetricNumber(latestPayload?.atr_bps))} bps`} />
        <Metric
          label="Pacing"
          value={`${fmtPrice(toNumber(config?.cooldown_minutes))}m`}
          detail={`Min ${fmtPrice(toNumber(config?.min_holding_minutes))}m / Max ${fmtPrice(toNumber(config?.max_holding_minutes))}m`}
        />
      </section>

      <section className="mb-4 grid gap-3 md:grid-cols-4">
        <Metric
          label="Daily Loss Stop"
          value={`$${fmtPrice(toNumber(config?.daily_max_loss))}`}
          detail="Pauses new entries"
        />
        <Metric
          label="Trade Limit"
          value={`${config?.max_trades_per_day ?? "—"}/day`}
          detail="Filled orders"
        />
        <Metric
          label="Fee Burn Stop"
          value={`$${fmtPrice(toNumber(config?.max_fee_burn_per_day))}`}
          detail="Daily simulated fees"
        />
        <Metric
          label="Loss Streak"
          value={`${config?.pause_after_loss_streak ?? "—"} losses`}
          detail="Pause threshold"
        />
      </section>

      <section className="rounded-lg border border-white/[0.08]">
        <div className="hidden grid-cols-[80px_1fr_1fr_1fr_1fr] border-b border-line bg-white/[0.03] px-3 py-2 text-xs text-muted md:grid">
          <span>Signal</span>
          <span>Strategy</span>
          <span className="text-right">Status</span>
          <span className="text-right">Reason</span>
          <span className="text-right">Time</span>
        </div>
        {signals.map((signal) => (
          <div
            key={signal.id}
            className="border-b border-white/[0.06] p-3 text-sm tabular-nums md:grid md:grid-cols-[80px_1fr_1fr_1fr_1fr] md:px-3 md:py-2"
          >
            <div className="mb-2 flex items-center justify-between md:mb-0 md:block">
              <span className={signal.signal === "buy" ? "text-buy" : signal.signal === "sell" ? "text-sell" : "text-muted"}>
                {signal.signal}
              </span>
              <span className="text-xs text-muted md:hidden">{new Date(signal.created_at).toLocaleTimeString()}</span>
            </div>
            <span className="font-medium text-white">{signal.strategy}</span>
            <MobileField label="Status" value={signal.status} valueClassName="text-muted" desktopAt="md" />
            <MobileField label="Reason" value={signal.reason ?? "—"} valueClassName="max-w-full truncate text-muted" desktopAt="md" />
            <span className="hidden text-right text-muted md:block">{new Date(signal.created_at).toLocaleTimeString()}</span>
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

function MobileField({
  label,
  value,
  valueClassName = "text-white",
  desktopAt = "sm"
}: {
  label: string;
  value: string;
  valueClassName?: string;
  desktopAt?: "sm" | "md" | "lg";
}) {
  const layoutClass = {
    sm: "flex items-center justify-between gap-3 py-1 sm:block sm:py-0 sm:text-right",
    md: "flex items-center justify-between gap-3 py-1 md:block md:py-0 md:text-right",
    lg: "flex items-center justify-between gap-3 py-1 lg:block lg:py-0 lg:text-right"
  }[desktopAt];
  const labelClass = {
    sm: "text-xs text-muted sm:hidden",
    md: "text-xs text-muted md:hidden",
    lg: "text-xs text-muted lg:hidden"
  }[desktopAt];
  return (
    <div className={layoutClass}>
      <span className={labelClass}>{label}</span>
      <span className={valueClassName}>{value}</span>
    </div>
  );
}

function ExperimentPanel({ experiments }: { experiments: SimulationExperiment[] }) {
  return (
    <section className="mt-5 rounded-lg border border-line bg-panel/90 p-4 shadow-2xl">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <LineChart className="h-4 w-4 text-accent" aria-hidden />
          <div>
            <h2 className="text-sm font-semibold text-ink">Forward Experiments</h2>
            <p className="mt-1 text-xs text-muted">Live paper results grouped by strategy configuration</p>
          </div>
        </div>
      </div>

      <section className="rounded-lg border border-white/[0.08]">
        <div className="hidden grid-cols-[70px_1fr_80px_90px_1fr_1fr_1fr_1fr_1fr] border-b border-line bg-white/[0.03] px-3 py-2 text-xs text-muted lg:grid">
          <span>ID</span>
          <span>Strategy</span>
          <span>Frame</span>
          <span>Status</span>
          <span className="text-right">Net PnL</span>
          <span className="text-right">Expectancy</span>
          <span className="text-right">Trades</span>
          <span className="text-right">PF</span>
          <span className="text-right">Verdict</span>
        </div>
        {experiments.map((experiment) => (
          <div
            key={experiment.id}
            className="border-b border-white/[0.06] p-3 text-sm tabular-nums lg:grid lg:grid-cols-[70px_1fr_80px_90px_1fr_1fr_1fr_1fr_1fr] lg:px-3 lg:py-2"
          >
            <div className="lg:hidden">
              <div className="mb-3 flex items-start justify-between gap-3">
                <div>
                  <div className="text-gold">#{experiment.id}</div>
                  <div className="mt-1 font-medium text-white">{experiment.strategy}</div>
                </div>
                <div className={experiment.status === "running" ? "text-buy" : "text-muted"}>{experiment.status}</div>
              </div>
              <MobileField label="Frame" value={experiment.interval} valueClassName="text-muted" desktopAt="lg" />
              <MobileField label="Net PnL" value={`$${fmtPrice(toNumber(experiment.pnl.net_realized_pnl))}`} desktopAt="lg" />
              <MobileField label="Expectancy" value={`$${fmtPrice(toNumber(experiment.scorecard?.expectancy_per_trade))}`} valueClassName="text-muted" desktopAt="lg" />
              <MobileField
                label="Trades"
                value={`${experiment.pnl.closed_trade_count} (${experiment.pnl.winning_trade_count}W/${experiment.pnl.losing_trade_count}L)`}
                valueClassName="text-muted"
                desktopAt="lg"
              />
              <MobileField
                label="PF"
                value={`${fmtPrice(toNumber(experiment.pnl.profit_factor))} / ${fmtPrice(toNumber(experiment.scorecard?.fee_drag_pct))}% fee`}
                valueClassName="text-muted"
                desktopAt="lg"
              />
              <MobileField label="Verdict" value={experiment.validation.status} valueClassName="text-muted" desktopAt="lg" />
            </div>
            <div className="hidden lg:contents">
              <span className="text-gold">#{experiment.id}</span>
              <span className="font-medium text-white">{experiment.strategy}</span>
              <span className="text-muted">{experiment.interval}</span>
              <span className={experiment.status === "running" ? "text-buy" : "text-muted"}>{experiment.status}</span>
              <span className="text-right text-white">${fmtPrice(toNumber(experiment.pnl.net_realized_pnl))}</span>
              <span className="text-right text-muted">${fmtPrice(toNumber(experiment.scorecard?.expectancy_per_trade))}</span>
              <span className="text-right text-muted">
                {experiment.pnl.closed_trade_count} ({experiment.pnl.winning_trade_count}W/{experiment.pnl.losing_trade_count}L)
              </span>
              <div className="text-right text-muted">
                {fmtPrice(toNumber(experiment.pnl.profit_factor))}
                <span className="ml-1 text-[11px] text-muted/70">
                  / {fmtPrice(toNumber(experiment.scorecard?.fee_drag_pct))}% fee
                </span>
              </div>
              <span className="truncate text-right text-muted" title={experiment.validation.reason}>
                {experiment.validation.status}
              </span>
            </div>
          </div>
        ))}
        {!experiments.length ? (
          <div className="px-3 py-4 text-sm text-muted">Start automation to create a forward-test experiment.</div>
        ) : null}
      </section>
    </section>
  );
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
          ["momentum_breakout", "Momentum Breakout"],
          ["pullback_reclaim", "Pullback Reclaim"]
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
            <BacktestInput
              label={strategy === "pullback_reclaim" ? "Support Window" : "Momentum Window"}
              value={momentumWindow}
              onChange={onMomentumWindowChange}
            />
            <BacktestInput
              label={strategy === "pullback_reclaim" ? "Reclaim bps" : "Breakout bps"}
              value={breakoutBps}
              onChange={onBreakoutBpsChange}
            />
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

function CollapsibleSection({
  title,
  defaultOpen,
  children
}: {
  title: string;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  return (
    <details className="mt-5 rounded-lg border border-line bg-panel/70 p-4 shadow-2xl" open={defaultOpen}>
      <summary className="cursor-pointer select-none text-sm font-semibold text-ink">{title}</summary>
      <div className="mt-4">{children}</div>
    </details>
  );
}

function Metric({
  label,
  value,
  detail,
  valueClassName = "text-white"
}: {
  label: string;
  value: string;
  detail: string;
  valueClassName?: string;
}) {
  return (
    <section className="rounded-lg border border-line bg-panel/90 p-4 shadow-2xl">
      <div className="text-xs uppercase text-muted">{label}</div>
      <div className={`mt-3 text-xl font-semibold tabular-nums ${valueClassName}`}>{value}</div>
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
