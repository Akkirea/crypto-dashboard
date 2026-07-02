"use client";

import { useEffect, useMemo, useRef } from "react";
import { createChart, IChartApi, ISeriesApi, Time } from "lightweight-charts";
import { CandleEvent, CandleInterval } from "@/lib/types";

const CANDLE_INTERVALS: CandleInterval[] = ["1m", "5m", "15m", "1h"];

export function CandleChart({
  candles,
  symbol,
  interval,
  onIntervalChange
}: {
  candles: CandleEvent[];
  symbol: string;
  interval: CandleInterval;
  onIntervalChange: (interval: CandleInterval) => void;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);

  const data = useMemo(
    () =>
      candles
        .slice(-120)
        .map((candle) => ({
          time: Math.floor(candle.open_time / 1000) as Time,
          open: candle.open,
          high: candle.high,
          low: candle.low,
          close: candle.close
        }))
        .sort((a, b) => Number(a.time) - Number(b.time)),
    [candles]
  );

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      height: 390,
      layout: {
        background: { color: "transparent" },
        textColor: "#b9b3c9"
      },
      grid: {
        vertLines: { color: "rgba(255,255,255,0.05)" },
        horzLines: { color: "rgba(255,255,255,0.06)" }
      },
      rightPriceScale: { borderColor: "rgba(255,255,255,0.1)" },
      timeScale: { borderColor: "rgba(255,255,255,0.1)", timeVisible: true },
      crosshair: { mode: 1 }
    });
    const series = chart.addCandlestickSeries({
      upColor: "#5ee0a0",
      downColor: "#ff6b7a",
      borderVisible: false,
      wickUpColor: "#5ee0a0",
      wickDownColor: "#ff6b7a"
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
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  useEffect(() => {
    seriesRef.current?.setData(data);
    chartRef.current?.timeScale().fitContent();
  }, [data]);

  return (
    <section className="rounded-lg border border-line bg-[linear-gradient(135deg,rgba(255,255,255,0.07),rgba(255,255,255,0.025)),#15151c] p-4 shadow-2xl">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-ink">{symbol} Candles</h2>
          <div className="text-xs text-muted">TradingView lightweight-charts</div>
        </div>
        <div className="inline-flex rounded-md border border-line bg-black/25 p-1">
          {CANDLE_INTERVALS.map((item) => (
            <button
              key={item}
              onClick={() => onIntervalChange(item)}
              className={`h-8 rounded px-3 text-sm ${
                interval === item ? "bg-accent text-black" : "text-muted hover:bg-white/5 hover:text-ink"
              }`}
            >
              {item}
            </button>
          ))}
        </div>
      </div>
      <div ref={containerRef} className="h-[390px] w-full" />
    </section>
  );
}
