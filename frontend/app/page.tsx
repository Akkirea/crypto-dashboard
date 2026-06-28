"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Activity,
  BarChart3,
  Bell,
  BookOpen,
  CalendarDays,
  LayoutDashboard,
  Search,
  ShieldCheck,
  WalletCards
} from "lucide-react";
import { CandleChart } from "@/components/CandleChart";
import { ConnectionHealth } from "@/components/ConnectionHealth";
import { OrderBook } from "@/components/OrderBook";
import { PriceTicker } from "@/components/PriceTicker";
import { TradeTape } from "@/components/TradeTape";
import { VolumePanel } from "@/components/VolumePanel";
import { BookTopEvent, CandleEvent, HealthEvent, MarketMessage, SymbolName, TradeEvent } from "@/lib/types";

const SYMBOLS: SymbolName[] = ["BTCUSDT", "ETHUSDT", "SOLUSDT"];
const WS_URL = process.env.NEXT_PUBLIC_BACKEND_WS_URL ?? "ws://localhost:8000/ws/market";

type CandlesBySymbol = Partial<Record<SymbolName, Partial<Record<"1m" | "5m", CandleEvent[]>>>>;

export default function DashboardPage() {
  const [selectedSymbol, setSelectedSymbol] = useState<SymbolName>("BTCUSDT");
  const [interval, setInterval] = useState<"1m" | "5m">("1m");
  const [prices, setPrices] = useState<Partial<Record<SymbolName, number>>>({});
  const [books, setBooks] = useState<Partial<Record<SymbolName, BookTopEvent>>>({});
  const [trades, setTrades] = useState<Partial<Record<SymbolName, TradeEvent[]>>>({});
  const [candles, setCandles] = useState<CandlesBySymbol>({});
  const [health, setHealth] = useState<HealthEvent>();
  const [socketState, setSocketState] = useState("connecting");

  useEffect(() => {
    let closed = false;
    let socket: WebSocket | null = null;
    let retryMs = 1000;

    function connect() {
      if (closed) return;
      setSocketState("connecting");
      socket = new WebSocket(WS_URL);

      socket.onopen = () => {
        retryMs = 1000;
        setSocketState("open");
      };

      socket.onmessage = (event) => {
        const message = JSON.parse(event.data) as MarketMessage;
        if (message.type === "snapshot") {
          setPrices(message.prices);
          setBooks(message.books);
          setTrades(message.trades);
          setHealth(message.health);
          const nextCandles: CandlesBySymbol = {};
          for (const symbol of SYMBOLS) {
            nextCandles[symbol] = {};
            for (const candleInterval of ["1m", "5m"] as const) {
              const candle = message.candles[symbol]?.[candleInterval];
              nextCandles[symbol]![candleInterval] = candle ? [candle] : [];
            }
          }
          setCandles(nextCandles);
          return;
        }

        if (message.type === "health") {
          setHealth(message);
          return;
        }

        if (message.type === "trade") {
          setPrices((current) => ({ ...current, [message.symbol]: message.price }));
          setTrades((current) => ({
            ...current,
            [message.symbol]: [message, ...(current[message.symbol] ?? [])].slice(0, 100)
          }));
          return;
        }

        if (message.type === "book_top") {
          setBooks((current) => ({ ...current, [message.symbol]: message }));
          return;
        }

        if (message.type === "candle") {
          setCandles((current) => {
            const existing = current[message.symbol]?.[message.interval] ?? [];
            const withoutCurrent = existing.filter((candle) => candle.open_time !== message.open_time);
            return {
              ...current,
              [message.symbol]: {
                ...(current[message.symbol] ?? {}),
                [message.interval]: [...withoutCurrent, message]
                  .sort((a, b) => a.open_time - b.open_time)
                  .slice(-180)
              }
            };
          });
        }
      };

      socket.onclose = () => {
        setSocketState("closed");
        if (!closed) {
          const delay = retryMs;
          retryMs = Math.min(15000, retryMs * 1.8);
          window.setTimeout(connect, delay);
        }
      };

      socket.onerror = () => {
        socket?.close();
      };
    }

    connect();
    return () => {
      closed = true;
      socket?.close();
    };
  }, []);

  const selectedCandles = candles[selectedSymbol]?.[interval] ?? [];
  const selectedBook = books[selectedSymbol];
  const selectedTrades = trades[selectedSymbol] ?? [];
  const candle1m = useMemo(() => candles[selectedSymbol]?.["1m"]?.at(-1), [candles, selectedSymbol]);
  const candle5m = useMemo(() => candles[selectedSymbol]?.["5m"]?.at(-1), [candles, selectedSymbol]);
  const totalMessages = Object.values(health?.message_counts ?? {}).reduce((sum, value) => sum + value, 0);

  return (
    <main className="min-h-screen p-3 text-ink sm:p-5">
      <div className="mx-auto grid min-h-[calc(100vh-2.5rem)] max-w-[1500px] grid-cols-1 overflow-hidden rounded-[28px] border border-white/15 bg-black/35 shadow-[0_24px_90px_rgba(0,0,0,0.55)] backdrop-blur-xl lg:grid-cols-[220px_minmax(0,1fr)]">
        <aside className="hidden border-r border-white/10 bg-black/25 p-5 lg:block">
          <div className="mb-8 flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-lg bg-accent text-black">
              <BarChart3 className="h-5 w-5" aria-hidden />
            </div>
            <div>
              <div className="text-sm font-semibold tracking-wide">CRYPTOS</div>
              <div className="text-xs text-muted">Market Intel</div>
            </div>
          </div>
          <nav className="space-y-2 text-sm">
            <Link
              href="/"
              className="flex h-10 w-full items-center gap-3 rounded-lg border border-white/10 bg-white/10 px-3 text-left text-white"
            >
              <LayoutDashboard className="h-4 w-4" aria-hidden />
              Dashboard
            </Link>
            <Link
              href="/analytics"
              className="flex h-10 w-full items-center gap-3 rounded-lg px-3 text-left text-muted hover:bg-white/5 hover:text-white"
            >
              <Activity className="h-4 w-4" aria-hidden />
              Analytics
            </Link>
            {[
              ["Research", BookOpen],
              ["Portfolio", WalletCards]
            ].map(([label, Icon]) => (
              <button
                key={label as string}
                className="flex h-10 w-full items-center gap-3 rounded-lg px-3 text-left text-muted hover:bg-white/5 hover:text-white"
              >
                <Icon className="h-4 w-4" aria-hidden />
                {label as string}
              </button>
            ))}
          </nav>
          <div className="mt-8 rounded-lg border border-white/10 bg-white/[0.04] p-3">
            <div className="flex items-center gap-2 text-xs text-muted">
              <ShieldCheck className="h-4 w-4 text-buy" aria-hidden />
              Read-only mode
            </div>
            <div className="mt-2 text-sm text-white">Public market streams only</div>
          </div>
        </aside>

        <section className="min-w-0 p-4 sm:p-5 lg:p-6">
          <header className="mb-5 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h1 className="text-2xl font-semibold tracking-normal text-white">Crypto Market Dashboard</h1>
              <div className="mt-1 flex items-center gap-2 text-sm text-muted">
                <ShieldCheck className="h-4 w-4 text-buy" aria-hidden />
                Read-only Binance public market data
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <div className="hidden h-10 min-w-[240px] items-center gap-2 rounded-lg border border-white/10 bg-white/[0.06] px-3 text-sm text-muted md:flex">
                <Search className="h-4 w-4" aria-hidden />
                Search markets
              </div>
              <div className="flex h-10 items-center gap-2 rounded-lg border border-white/10 bg-white/[0.06] px-3 text-sm text-muted">
                <CalendarDays className="h-4 w-4" aria-hidden />
                Live session
              </div>
              <button className="grid h-10 w-10 place-items-center rounded-lg border border-white/10 bg-white/[0.06] text-muted hover:text-white">
                <Bell className="h-4 w-4" aria-hidden />
              </button>
            </div>
          </header>

          <section className="mb-5 grid gap-3 md:grid-cols-3 xl:grid-cols-[1fr_1fr_1fr_180px]">
            {SYMBOLS.map((symbol) => (
              <PriceTicker
                key={symbol}
                symbol={symbol}
                price={prices[symbol]}
                book={books[symbol]}
                selected={selectedSymbol === symbol}
                onSelect={() => setSelectedSymbol(symbol)}
              />
            ))}
            <div className="rounded-lg border border-line bg-[linear-gradient(135deg,rgba(91,231,255,0.12),rgba(231,213,111,0.06)),#15151c] p-4 shadow-2xl">
              <div className="text-xs uppercase text-muted">Messages</div>
              <div className="mt-3 text-2xl font-semibold tabular-nums text-white">
                {totalMessages.toLocaleString()}
              </div>
              <div className="mt-2 text-xs text-muted">
                WS <span className="font-medium capitalize text-buy">{socketState}</span>
              </div>
            </div>
          </section>

          <section className="grid gap-4 xl:grid-cols-[minmax(0,1.55fr)_330px_340px]">
            <div className="min-w-0">
              <CandleChart
                candles={selectedCandles}
                symbol={selectedSymbol}
                interval={interval}
                onIntervalChange={setInterval}
              />
            </div>
            <div className="grid content-start gap-4">
              <OrderBook book={selectedBook} />
              <VolumePanel candle1m={candle1m} candle5m={candle5m} />
              <ConnectionHealth health={health} />
            </div>
            <TradeTape trades={selectedTrades} />
          </section>
        </section>
      </div>
    </main>
  );
}
