"use client";

import { useEffect, useState } from "react";
import { AnalyticsEventFeed } from "@/components/analytics/AnalyticsEventFeed";
import { AnalyticsShell } from "@/components/analytics/AnalyticsShell";
import { CrossExchangePanel } from "@/components/analytics/CrossExchangePanel";
import { MetricCard } from "@/components/analytics/MetricCard";
import { SpreadRankingTable } from "@/components/analytics/SpreadRankingTable";
import { TrendRankTable } from "@/components/analytics/TrendRankTable";
import { VolatilityRegimePanel } from "@/components/analytics/VolatilityRegimePanel";
import { VolumeAnomalyPanel } from "@/components/analytics/VolumeAnomalyPanel";
import { LiquidityMonitor } from "@/components/analytics/LiquidityMonitor";
import { HistoricalAnalyticsChart } from "@/components/analytics/HistoricalAnalyticsChart";
import { OrderBookRollupChart } from "@/components/analytics/OrderBookRollupChart";
import { StorageOpsPanel } from "@/components/analytics/StorageOpsPanel";
import {
  AnalyticsEvent,
  AnalyticsHistorySnapshot,
  AnalyticsStorageSummary,
  AnalyticsSummary,
  DatabaseHealth,
  OrderBookRollupPoint
} from "@/lib/analyticsTypes";
import { backendHttpUrl } from "@/lib/backendConfig";
import { fmtPrice } from "@/lib/format";

export default function AnalyticsPage() {
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [events, setEvents] = useState<AnalyticsEvent[]>([]);
  const [history, setHistory] = useState<AnalyticsHistorySnapshot[]>([]);
  const [storage, setStorage] = useState<AnalyticsStorageSummary | null>(null);
  const [databaseHealth, setDatabaseHealth] = useState<DatabaseHealth | null>(null);
  const [rollups, setRollups] = useState<OrderBookRollupPoint[]>([]);
  const [rollupSymbol, setRollupSymbol] = useState("BTCUSDT");
  const [error, setError] = useState<string | null>(null);
  const [apiUrl, setApiUrl] = useState<string>("");

  useEffect(() => {
    let closed = false;

    async function load() {
      try {
        const httpUrl = backendHttpUrl();
        if (!closed) setApiUrl(httpUrl);
        const response = await fetch(`${httpUrl}/api/analytics/summary`, { cache: "no-store" });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = (await response.json()) as AnalyticsSummary;
        if (!closed) {
          setSummary(data);
          setError(null);
        }
      } catch (caught) {
        if (!closed) {
          setError(caught instanceof Error ? caught.message : "analytics unavailable");
        }
      }
    }

    async function loadEvents() {
      try {
        const httpUrl = backendHttpUrl();
        const response = await fetch(`${httpUrl}/api/analytics/events?limit=25`, {
          cache: "no-store"
        });
        if (!response.ok) return;
        const data = (await response.json()) as AnalyticsEvent[];
        if (!closed) setEvents(data);
      } catch (caught) {
        console.warn("analytics events unavailable", caught);
      }
    }

    async function loadHistory() {
      try {
        const httpUrl = backendHttpUrl();
        const response = await fetch(`${httpUrl}/api/analytics/history?metric_family=summary&limit=30`, {
          cache: "no-store"
        });
        if (!response.ok) return;
        const data = (await response.json()) as AnalyticsHistorySnapshot[];
        if (!closed) setHistory(data);
      } catch (caught) {
        console.warn("analytics history unavailable", caught);
      }
    }

    async function loadStorage() {
      try {
        const httpUrl = backendHttpUrl();
        const [healthResponse, storageResponse] = await Promise.all([
          fetch(`${httpUrl}/health/database`, { cache: "no-store" }),
          fetch(`${httpUrl}/api/analytics/storage`, { cache: "no-store" })
        ]);
        if (healthResponse.ok) {
          const data = (await healthResponse.json()) as DatabaseHealth;
          if (!closed) setDatabaseHealth(data);
        }
        if (storageResponse.ok) {
          const data = (await storageResponse.json()) as AnalyticsStorageSummary;
          if (!closed) setStorage(data);
        }
      } catch (caught) {
        console.warn("storage analytics unavailable", caught);
      }
    }

    load();
    loadEvents();
    loadHistory();
    loadStorage();
    const summaryInterval = window.setInterval(load, 3000);
    const eventsInterval = window.setInterval(loadEvents, 10000);
    const historyInterval = window.setInterval(loadHistory, 60000);
    const storageInterval = window.setInterval(loadStorage, 30000);
    return () => {
      closed = true;
      window.clearInterval(summaryInterval);
      window.clearInterval(eventsInterval);
      window.clearInterval(historyInterval);
      window.clearInterval(storageInterval);
    };
  }, []);

  useEffect(() => {
    let closed = false;

    async function loadRollups() {
      try {
        const httpUrl = backendHttpUrl();
        const response = await fetch(
          `${httpUrl}/api/analytics/rollups/order-book?symbol=${rollupSymbol}&limit=720`,
          { cache: "no-store" }
        );
        if (!response.ok) return;
        const data = (await response.json()) as OrderBookRollupPoint[];
        if (!closed) setRollups(data);
      } catch (caught) {
        console.warn("order book rollups unavailable", caught);
      }
    }

    loadRollups();
    const interval = window.setInterval(loadRollups, 60000);
    return () => {
      closed = true;
      window.clearInterval(interval);
    };
  }, [rollupSymbol]);

  const trendLeader = summary?.leaders.trend;
  const tightest = summary?.leaders.tightest_spread;
  const volatile = summary?.leaders.most_volatile;

  return (
    <AnalyticsShell>
      <section className="mb-5 grid gap-3 md:grid-cols-3">
        <MetricCard
          label="Trending Market"
          value={trendLeader?.symbol ?? "—"}
          detail={`Momentum ${trendLeader ? trendLeader.momentum_score.toFixed(2) : "—"}`}
          tone="accent"
        />
        <MetricCard
          label="Tightest Spread"
          value={tightest?.symbol ?? "—"}
          detail={`${fmtPrice(tightest?.average_spread_bps)} avg bps on ${tightest?.exchange ?? "—"}`}
          tone="buy"
        />
        <MetricCard
          label="Most Volatile"
          value={volatile?.symbol ?? "—"}
          detail={`${fmtPrice(volatile?.realized_volatility_pct)}% realized · ${volatile?.regime ?? "—"}`}
          tone="gold"
        />
      </section>

      {error ? (
        <section className="rounded-lg border border-sell/30 bg-sell/10 p-4 text-sm text-sell">
          <div>Analytics API unavailable: {error}</div>
          <div className="mt-2 break-all text-xs text-slate-400">Endpoint: {apiUrl || "unknown"}</div>
        </section>
      ) : null}

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_minmax(320px,0.8fr)]">
        <div className="grid gap-4">
          <HistoricalAnalyticsChart snapshots={history} />
          <OrderBookRollupChart
            points={rollups}
            symbol={rollupSymbol}
            onSymbolChange={setRollupSymbol}
          />
          <TrendRankTable rows={summary?.trend_rankings ?? []} />
          <VolumeAnomalyPanel rows={summary?.volume_anomalies ?? []} />
          <AnalyticsEventFeed events={events} />
        </div>
        <div className="grid gap-4">
          <StorageOpsPanel health={databaseHealth} storage={storage} />
          <SpreadRankingTable rows={summary?.spread_rankings ?? []} />
          <CrossExchangePanel rows={summary?.cross_exchange ?? []} />
          <LiquidityMonitor rows={summary?.liquidity ?? []} />
        </div>
        <VolatilityRegimePanel rows={summary?.volatility_rankings ?? []} />
      </section>
    </AnalyticsShell>
  );
}
