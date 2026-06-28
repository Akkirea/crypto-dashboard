import { VolatilityRow } from "@/lib/analyticsTypes";
import { fmtPrice } from "@/lib/format";

const regimeClass: Record<string, string> = {
  quiet: "border-buy/20 bg-buy/10 text-buy",
  normal: "border-cyan/20 bg-cyan/10 text-cyan",
  elevated: "border-gold/20 bg-gold/10 text-gold",
  extreme: "border-sell/20 bg-sell/10 text-sell",
  insufficient_data: "border-white/10 bg-white/[0.04] text-muted"
};

export function VolatilityRegimePanel({ rows }: { rows: VolatilityRow[] }) {
  return (
    <section className="rounded-lg border border-line bg-panel/90 p-4 shadow-2xl">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ink">Volatility Regime</h2>
        <span className="rounded-full border border-white/10 px-2 py-1 text-xs text-muted">Realized</span>
      </div>
      <div className="space-y-3">
        {rows.map((row) => (
          <div key={row.symbol} className="rounded-lg border border-white/10 bg-white/[0.035] p-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="font-medium text-white">{row.symbol}</div>
                <div className="text-xs text-muted">
                  Range {fmtPrice(row.average_candle_range_pct)}% · Samples {row.sample_count}
                </div>
              </div>
              <span className={`rounded-full border px-2 py-1 text-xs capitalize ${regimeClass[row.regime]}`}>
                {row.regime.replace("_", " ")}
              </span>
            </div>
            <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/10">
              <div
                className="h-full rounded-full bg-accent"
                style={{
                  width: `${Math.min(100, Math.max(4, row.realized_volatility_pct ?? 4))}%`
                }}
              />
            </div>
            <div className="mt-2 text-right text-xs tabular-nums text-muted">
              {fmtPrice(row.realized_volatility_pct)}% annualized
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
