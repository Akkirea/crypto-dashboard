"use client";

import { useEffect, useMemo, useRef } from "react";
import { createChart, IChartApi, ISeriesApi, Time } from "lightweight-charts";
import { BarChart3 } from "lucide-react";
import { OrderBookRollupPoint } from "@/lib/analyticsTypes";
import { fmtPrice, fmtUsdCompact, toNumber } from "@/lib/format";

function asTime(value: string) {
  const parsed = Date.parse(value);
  return Math.floor((Number.isNaN(parsed) ? Date.now() : parsed) / 1000) as Time;
}

export function OrderBookRollupChart({
  points,
  symbol,
  onSymbolChange
}: {
  points: OrderBookRollupPoint[];
  symbol: string;
  onSymbolChange: (symbol: string) => void;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const spreadSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const depthSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);

  const chartData = useMemo(() => {
    const grouped = new Map<number, { spread: number; depth: number }>();
    for (const point of points) {
      const spread = toNumber(point.avg_spread_bps);
      const bidNotional = toNumber(point.avg_top_bid_notional);
      const askNotional = toNumber(point.avg_top_ask_notional);
      if (spread === null) continue;
      grouped.set(Number(asTime(point.bucket_start)), {
        spread,
        depth: (bidNotional ?? 0) + (askNotional ?? 0)
      });
    }

    return [...grouped.entries()]
      .map(([time, value]) => ({
        time: time as Time,
        spread: value.spread,
        depth: value.depth
      }))
      .sort((a, b) => Number(a.time) - Number(b.time));
  }, [points]);

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      height: 260,
      layout: { background: { color: "transparent" }, textColor: "#b9b3c9" },
      grid: {
        vertLines: { color: "rgba(255,255,255,0.05)" },
        horzLines: { color: "rgba(255,255,255,0.06)" }
      },
      rightPriceScale: { borderColor: "rgba(255,255,255,0.1)" },
      leftPriceScale: { borderColor: "rgba(255,255,255,0.1)", visible: true },
      timeScale: { borderColor: "rgba(255,255,255,0.1)", timeVisible: true }
    });
    const spreadSeries = chart.addLineSeries({
      color: "#5be7ff",
      lineWidth: 2,
      priceLineVisible: false,
      title: "Spread bps"
    });
    const depthSeries = chart.addLineSeries({
      color: "#e7d56f",
      lineWidth: 2,
      priceLineVisible: false,
      priceScaleId: "left",
      title: "Top depth"
    });

    chartRef.current = chart;
    spreadSeriesRef.current = spreadSeries;
    depthSeriesRef.current = depthSeries;

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
    spreadSeriesRef.current?.setData(chartData.map((point) => ({ time: point.time, value: point.spread })));
    depthSeriesRef.current?.setData(chartData.map((point) => ({ time: point.time, value: point.depth })));
    chartRef.current?.timeScale().fitContent();
  }, [chartData]);

  const latest = chartData.at(-1);

  return (
    <section className="rounded-lg border border-line bg-panel/90 p-4 shadow-2xl">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-ink">Order Book Rollups</h2>
          <div className="mt-1 text-xs text-muted">
            1-minute spread and top-of-book notional history
          </div>
        </div>
        <div className="flex items-center gap-2">
          {["BTCUSDT", "ETHUSDT", "SOLUSDT"].map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => onSymbolChange(option)}
              className={`h-8 rounded-lg border px-2 text-xs font-medium ${
                symbol === option
                  ? "border-accent/50 bg-accent/20 text-white"
                  : "border-white/10 bg-white/[0.05] text-muted hover:text-white"
              }`}
            >
              {option.replace("USDT", "")}
            </button>
          ))}
        </div>
      </div>

      <div className="mb-3 grid gap-3 sm:grid-cols-3">
        <div className="rounded-lg border border-white/10 bg-white/[0.04] p-3">
          <div className="flex items-center gap-2 text-xs text-muted">
            <BarChart3 className="h-4 w-4 text-accent" aria-hidden />
            Points
          </div>
          <div className="mt-2 text-lg font-semibold tabular-nums text-white">{chartData.length}</div>
        </div>
        <div className="rounded-lg border border-white/10 bg-white/[0.04] p-3">
          <div className="text-xs text-muted">Latest spread</div>
          <div className="mt-2 text-lg font-semibold tabular-nums text-accent">
            {fmtPrice(latest?.spread)} bps
          </div>
        </div>
        <div className="rounded-lg border border-white/10 bg-white/[0.04] p-3">
          <div className="text-xs text-muted">Latest top depth</div>
          <div className="mt-2 text-lg font-semibold tabular-nums text-gold">
            {fmtUsdCompact(latest?.depth)}
          </div>
        </div>
      </div>

      <div ref={containerRef} className="h-[260px] w-full" />
    </section>
  );
}
