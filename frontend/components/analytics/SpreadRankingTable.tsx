import { SpreadRow } from "@/lib/analyticsTypes";
import { fmtPrice } from "@/lib/format";

export function SpreadRankingTable({ rows }: { rows: SpreadRow[] }) {
  return (
    <section className="rounded-lg border border-line bg-panel/90 p-4 shadow-2xl">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ink">Spread Analytics</h2>
        <span className="rounded-full border border-white/10 px-2 py-1 text-xs text-muted">5m average</span>
      </div>
      <div className="grid grid-cols-[44px_1fr_1fr_1fr] border-b border-line pb-2 text-xs text-muted">
        <span>Rank</span>
        <span>Market</span>
        <span className="text-right">Avg bps</span>
        <span className="text-right">Vol bps</span>
      </div>
      {rows.map((row) => (
        <div
          key={`${row.exchange}-${row.symbol}`}
          className="grid grid-cols-[44px_1fr_1fr_1fr] border-b border-white/[0.06] py-2 text-sm tabular-nums"
        >
          <span className="text-muted">#{row.tightness_rank}</span>
          <span className="font-medium text-white">{row.symbol}</span>
          <span className="text-right text-buy">{fmtPrice(row.average_spread_bps)}</span>
          <span className="text-right text-ink">{fmtPrice(row.spread_volatility_bps)}</span>
        </div>
      ))}
    </section>
  );
}
