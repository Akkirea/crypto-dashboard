import { TrendRow } from "@/lib/analyticsTypes";
import { fmtPrice, fmtQty } from "@/lib/format";

function pct(value: number | null | undefined) {
  if (value === null || value === undefined) return "—";
  return `${value.toFixed(2)}%`;
}

export function TrendRankTable({ rows }: { rows: TrendRow[] }) {
  return (
    <section className="rounded-lg border border-line bg-panel/90 p-4 shadow-2xl">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ink">Trend Rank</h2>
        <span className="rounded-full border border-white/10 px-2 py-1 text-xs text-muted">Momentum</span>
      </div>
      <div className="grid grid-cols-[44px_1fr_1fr_1fr_1fr] border-b border-line pb-2 text-xs text-muted">
        <span>Rank</span>
        <span>Symbol</span>
        <span className="text-right">Price</span>
        <span className="text-right">5m Chg</span>
        <span className="text-right">Score</span>
      </div>
      {rows.map((row) => (
        <div
          key={row.symbol}
          className="grid grid-cols-[44px_1fr_1fr_1fr_1fr] border-b border-white/[0.06] py-2 text-sm tabular-nums"
        >
          <span className="text-muted">#{row.rank}</span>
          <span className="font-medium text-white">{row.symbol}</span>
          <span className="text-right text-ink">${fmtPrice(row.latest_price)}</span>
          <span className={row.windows["5m"]?.price_change_pct ?? 0 >= 0 ? "text-right text-buy" : "text-right text-sell"}>
            {pct(row.windows["5m"]?.price_change_pct)}
          </span>
          <span className="text-right text-accent">{row.momentum_score.toFixed(2)}</span>
        </div>
      ))}
      <div className="mt-3 text-xs text-muted">
        Volume 5m leader: {rows[0] ? fmtQty(rows[0].windows["5m"]?.volume) : "—"} base units
      </div>
    </section>
  );
}
