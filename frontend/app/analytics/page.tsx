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
import { AnalyticsEvent, AnalyticsHistorySnapshot, AnalyticsSummary } from "@/lib/analyticsTypes";
import { fmtPrice } from "@/lib/format";

const HTTP_URL = process.env.NEXT_PUBLIC_BACKEND_HTTP_URL ?? "http://localhost:8000";

export default function AnalyticsPage() {
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [events, setEvents] = useState<AnalyticsEvent[]>([]);
  const [history, setHistory] = useState<AnalyticsHistorySnapshot[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let closed = false;

    async function load() {
      try {
        const response = await fetch(`${HTTP_URL}/api/analytics/summary`, { cache: "no-store" });
        const eventsResponse = await fetch(`${HTTP_URL}/api/analytics/events?limit=25`, {
          cache: "no-store"
        });
        const historyResponse = await fetch(`${HTTP_URL}/api/analytics/history?metric_family=summary&limit=120`, {
          cache: "no-store"
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        if (!eventsResponse.ok) throw new Error(`events HTTP ${eventsResponse.status}`);
        if (!historyResponse.ok) throw new Error(`history HTTP ${historyResponse.status}`);
        const data = (await response.json()) as AnalyticsSummary;
        const eventData = (await eventsResponse.json()) as AnalyticsEvent[];
        const historyData = (await historyResponse.json()) as AnalyticsHistorySnapshot[];
        if (!closed) {
          setSummary(data);
          setEvents(eventData);
          setHistory(historyData);
          setError(null);
        }
      } catch (caught) {
        if (!closed) setError(caught instanceof Error ? caught.message : "analytics unavailable");
      }
    }

    load();
    const interval = window.setInterval(load, 3000);
    return () => {
      closed = true;
      window.clearInterval(interval);
    };
  }, []);

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
          Analytics API unavailable: {error}
        </section>
      ) : null}

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_minmax(320px,0.8fr)]">
        <div className="grid gap-4">
          <HistoricalAnalyticsChart snapshots={history} />
          <TrendRankTable rows={summary?.trend_rankings ?? []} />
          <VolumeAnomalyPanel rows={summary?.volume_anomalies ?? []} />
          <AnalyticsEventFeed events={events} />
        </div>
        <div className="grid gap-4">
          <SpreadRankingTable rows={summary?.spread_rankings ?? []} />
          <CrossExchangePanel rows={summary?.cross_exchange ?? []} />
          <LiquidityMonitor rows={summary?.liquidity ?? []} />
        </div>
        <VolatilityRegimePanel rows={summary?.volatility_rankings ?? []} />
      </section>
    </AnalyticsShell>
  );
}
