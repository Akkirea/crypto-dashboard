"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { AreaSeriesPartialOptions, createChart, IChartApi, ISeriesApi, Time } from "lightweight-charts";
import { Activity, TrendingDown, TrendingUp } from "lucide-react";
import { backendHttpUrl } from "@/lib/backendConfig";

type ApiCandle = {
  open_time: string;
  close_time: string;
  open: string | number;
  high: string | number;
  low: string | number;
  close: string | number;
  volume: string | number;
};

const areaOptions: AreaSeriesPartialOptions = {
  lineColor: "#5be7ff",
  topColor: "rgba(91, 231, 255, 0.28)",
  bottomColor: "rgba(91, 231, 255, 0.02)",
  lineWidth: 2,
  priceLineVisible: false
};

function asNumber(value: string | number | undefined): number {
  if (value === undefined) return 0;
  const next = Number(value);
  return Number.isFinite(next) ? next : 0;
}

function fmtUsd(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: value >= 1000 ? 0 : 2
  }).format(value);
}

function fmtCompact(value: number): string {
  if (!Number.isFinite(value)) return "—";
  return new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 2
  }).format(value);
}

export function Btc24hChart() {
  const [candles, setCandles] = useState<ApiCandle[]>([]);
  const [error, setError] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Area"> | null>(null);

  useEffect(() => {
    let closed = false;

    async function loadCandles() {
      try {
        const response = await fetch(
          `${backendHttpUrl()}/api/simulation/market/candles?symbol=BTCUSDT&interval=5m&limit=288`,
          { cache: "no-store" }
        );
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = (await response.json()) as ApiCandle[];
        if (!closed) {
          setCandles(data);
          setError(null);
        }
      } catch (caught) {
        if (!closed) setError(caught instanceof Error ? caught.message : "BTC chart unavailable");
      }
    }

    loadCandles();
    const interval = window.setInterval(loadCandles, 30000);
    return () => {
      closed = true;
      window.clearInterval(interval);
    };
  }, []);

  const chartData = useMemo(
    () =>
      candles
        .map((candle) => ({
          time: Math.floor(new Date(candle.open_time).getTime() / 1000) as Time,
          value: asNumber(candle.close)
        }))
        .filter((point) => Number.isFinite(Number(point.time)) && point.value > 0)
        .sort((a, b) => Number(a.time) - Number(b.time)),
    [candles]
  );

  const stats = useMemo(() => {
    if (candles.length === 0) {
      return { open: 0, close: 0, high: 0, low: 0, volume: 0, changePct: null as number | null };
    }
    const sorted = candles
      .slice()
      .sort((a, b) => new Date(a.open_time).getTime() - new Date(b.open_time).getTime());
    const first = sorted[0];
    const last = sorted.at(-1)!;
    const open = asNumber(first.open);
    const close = asNumber(last.close);
    const high = Math.max(...sorted.map((candle) => asNumber(candle.high)).filter((value) => value > 0));
    const low = Math.min(...sorted.map((candle) => asNumber(candle.low)).filter((value) => value > 0));
    const volume = sorted.reduce((sum, candle) => sum + asNumber(candle.volume), 0);
    return {
      open,
      close,
      high: Number.isFinite(high) ? high : 0,
      low: Number.isFinite(low) ? low : 0,
      volume,
      changePct: open > 0 ? ((close - open) / open) * 100 : null
    };
  }, [candles]);

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      height: 260,
      layout: {
        background: { color: "transparent" },
        textColor: "#b9b3c9"
      },
      grid: {
        vertLines: { color: "rgba(255,255,255,0.045)" },
        horzLines: { color: "rgba(255,255,255,0.055)" }
      },
      rightPriceScale: { borderColor: "rgba(255,255,255,0.08)" },
      timeScale: { borderColor: "rgba(255,255,255,0.08)", timeVisible: true },
      crosshair: { mode: 1 }
    });
    const series = chart.addAreaSeries(areaOptions);
    chartRef.current = chart;
    seriesRef.current = series;

    const resize = () => {
      if (containerRef.current) chart.applyOptions({ width: containerRef.current.clientWidth });
    };
    resize();
    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  useEffect(() => {
    seriesRef.current?.setData(chartData);
    chartRef.current?.timeScale().fitContent();
  }, [chartData]);

  const isUp = (stats.changePct ?? 0) >= 0;
  const TrendIcon = isUp ? TrendingUp : TrendingDown;

  return (
    <section className="mb-5 rounded-lg border border-white/10 bg-[linear-gradient(135deg,rgba(91,231,255,0.08),rgba(231,213,111,0.045)),#15151c] p-4 shadow-2xl">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-muted">
            <Activity className="h-4 w-4 text-accent" aria-hidden />
            24h BTC-USD
          </div>
          <div className="mt-2 flex flex-wrap items-end gap-3">
            <h2 className="text-3xl font-semibold tracking-normal text-white">{fmtUsd(stats.close)}</h2>
            <div className={`mb-1 flex items-center gap-1 text-sm font-medium ${isUp ? "text-buy" : "text-sell"}`}>
              <TrendIcon className="h-4 w-4" aria-hidden />
              {stats.changePct === null ? "—" : `${stats.changePct >= 0 ? "+" : ""}${stats.changePct.toFixed(2)}%`}
            </div>
          </div>
        </div>
        <div className="grid grid-cols-3 gap-2 text-right text-xs sm:min-w-[320px]">
          <div className="rounded-lg border border-white/10 bg-black/20 p-2">
            <div className="text-muted">High</div>
            <div className="mt-1 font-medium text-white">{fmtUsd(stats.high)}</div>
          </div>
          <div className="rounded-lg border border-white/10 bg-black/20 p-2">
            <div className="text-muted">Low</div>
            <div className="mt-1 font-medium text-white">{fmtUsd(stats.low)}</div>
          </div>
          <div className="rounded-lg border border-white/10 bg-black/20 p-2">
            <div className="text-muted">Volume</div>
            <div className="mt-1 font-medium text-white">{fmtCompact(stats.volume)} BTC</div>
          </div>
        </div>
      </div>
      <div ref={containerRef} className="h-[260px] w-full" />
      {error ? <div className="mt-3 text-xs text-sell">{error}</div> : null}
    </section>
  );
}
