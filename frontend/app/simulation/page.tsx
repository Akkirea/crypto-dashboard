"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ChevronLeft, Database, PlaySquare, ShieldCheck, SlidersHorizontal } from "lucide-react";
import { backendHttpUrl } from "@/lib/backendConfig";
import { fmtPrice, toNumber } from "@/lib/format";
import {
  SimulationCandle,
  SimulationConfig,
  SimulationSnapshot,
  SimulationTrade
} from "@/lib/simulationTypes";

export default function SimulationPage() {
  const [config, setConfig] = useState<SimulationConfig | null>(null);
  const [snapshot, setSnapshot] = useState<SimulationSnapshot | null>(null);
  const [candles, setCandles] = useState<SimulationCandle[]>([]);
  const [trades, setTrades] = useState<SimulationTrade[]>([]);
  const [symbol, setSymbol] = useState("BTCUSDT");
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
        const [snapshotResponse, candleResponse, tradeResponse] = await Promise.all([
          fetch(`${httpUrl}/api/simulation/market/snapshot`, { cache: "no-store" }),
          fetch(`${httpUrl}/api/simulation/market/candles?symbol=${symbol}&interval=1m&limit=12`, {
            cache: "no-store"
          }),
          fetch(`${httpUrl}/api/simulation/market/trades?symbol=${symbol}&limit=12`, {
            cache: "no-store"
          })
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
  }, [symbol]);

  const selectedBook = snapshot?.books[symbol];
  const latestCandle = candles.at(-1);
  const latestTrade = trades.at(-1);
  const totalMessages = useMemo(
    () => Object.values(snapshot?.health.message_counts ?? {}).reduce((sum, value) => sum + value, 0),
    [snapshot]
  );

  return (
    <main className="min-h-screen p-3 text-ink sm:p-5">
      <div className="mx-auto min-h-[calc(100vh-2.5rem)] max-w-[1500px] overflow-hidden rounded-[28px] border border-white/15 bg-black/35 shadow-[0_24px_90px_rgba(0,0,0,0.55)] backdrop-blur-xl">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 p-5">
          <div className="flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-lg bg-gold text-black">
              <PlaySquare className="h-5 w-5" aria-hidden />
            </div>
            <div>
              <h1 className="text-2xl font-semibold text-white">Simulation Foundation</h1>
              <div className="mt-1 flex items-center gap-2 text-sm text-muted">
                <ShieldCheck className="h-4 w-4 text-buy" aria-hidden />
                Read-only market data contracts
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
            <Metric label="Latest Trade" value={fmtPrice(toNumber(latestTrade?.price))} detail={symbol} />
            <Metric label="Spread" value={`${fmtPrice(selectedBook?.spread_bps)} bps`} detail="Top of book" />
          </section>

          <section className="grid gap-4 xl:grid-cols-[320px_minmax(0,1fr)_minmax(340px,0.9fr)]">
            <section className="rounded-lg border border-line bg-panel/90 p-4 shadow-2xl">
              <div className="mb-3 flex items-center gap-2">
                <SlidersHorizontal className="h-4 w-4 text-gold" aria-hidden />
                <h2 className="text-sm font-semibold text-ink">Fill Assumptions</h2>
              </div>
              <div className="space-y-3 text-sm">
                <Row label="Price source" value={config?.fill_model.price_source ?? "—"} />
                <Row label="Fee" value={`${config?.fill_model.fee_bps ?? "—"} bps`} />
                <Row label="Slippage" value={`${config?.fill_model.slippage_bps ?? "—"} bps`} />
                <Row label="Latency" value={`${config?.fill_model.latency_ms ?? "—"} ms`} />
                <Row label="Exchange" value={config?.default_exchange ?? "—"} />
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
        </section>
      </div>
    </main>
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
