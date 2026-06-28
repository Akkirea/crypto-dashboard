"use client";

import { useEffect, useMemo, useRef } from "react";
import { createChart, IChartApi, ISeriesApi, Time } from "lightweight-charts";
import { AnalyticsHistorySnapshot, AnalyticsSummary } from "@/lib/analyticsTypes";
import { fmtTime } from "@/lib/format";

function asMs(value: number | string | undefined) {
  if (typeof value === "number") return value;
  if (!value) return Date.now();
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? Date.now() : parsed;
}

function isSummary(payload: AnalyticsHistorySnapshot["payload"]): payload is AnalyticsSummary {
  return (payload as AnalyticsSummary).type === "analytics_summary";
}

export function HistoricalAnalyticsChart({
  snapshots
}: {
  snapshots: AnalyticsHistorySnapshot[];
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Line"> | null>(null);

  const points = useMemo(
    () =>
      snapshots
        .map((snapshot) => {
          const payload = snapshot.payload;
          const leader = isSummary(payload) ? payload.leaders.trend : null;
          return {
            time: Math.floor(asMs(snapshot.computed_at) / 1000) as Time,
            value: leader?.momentum_score ?? 0
          };
        })
        .sort((a, b) => Number(a.time) - Number(b.time)),
    [snapshots]
  );

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      height: 240,
      layout: { background: { color: "transparent" }, textColor: "#b9b3c9" },
      grid: {
        vertLines: { color: "rgba(255,255,255,0.05)" },
        horzLines: { color: "rgba(255,255,255,0.06)" }
      },
      rightPriceScale: { borderColor: "rgba(255,255,255,0.1)" },
      timeScale: { borderColor: "rgba(255,255,255,0.1)", timeVisible: true }
    });
    const series = chart.addLineSeries({
      color: "#c4b5fd",
      lineWidth: 2,
      priceLineVisible: false
    });
    chartRef.current = chart;
    seriesRef.current = series;

    const resize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    resize();
    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
      chart.remove();
    };
  }, []);

  useEffect(() => {
    seriesRef.current?.setData(points);
    chartRef.current?.timeScale().fitContent();
  }, [points]);

  const latest = snapshots.at(-1);

  return (
    <section className="rounded-lg border border-line bg-panel/90 p-4 shadow-2xl">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-ink">Historical Trend</h2>
          <div className="text-xs text-muted">
            {snapshots.length > 1
              ? `${snapshots.length} persisted snapshots`
              : "Enable Postgres persistence for a full history"}
          </div>
        </div>
        <span className="rounded-full border border-white/10 px-2 py-1 text-xs text-muted">
          {latest ? fmtTime(asMs(latest.computed_at)) : "—"}
        </span>
      </div>
      <div ref={containerRef} className="h-[240px] w-full" />
    </section>
  );
}
