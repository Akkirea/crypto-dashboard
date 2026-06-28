import { VolumeAnomalyRow } from "@/lib/analyticsTypes";
import { fmtPrice, fmtQty } from "@/lib/format";

export function VolumeAnomalyPanel({ rows }: { rows: VolumeAnomalyRow[] }) {
  return (
    <section className="rounded-lg border border-line bg-panel/90 p-4 shadow-2xl">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ink">Abnormal Volume</h2>
        <span className="rounded-full border border-white/10 px-2 py-1 text-xs text-muted">
          1m z-score
        </span>
      </div>
      <div className="grid grid-cols-[1fr_1fr_1fr_1fr] border-b border-line pb-2 text-xs text-muted">
        <span>Market</span>
        <span className="text-right">Volume</span>
        <span className="text-right">Base</span>
        <span className="text-right">Z</span>
      </div>
      {rows.map((row) => (
        <div
          key={`${row.exchange}-${row.symbol}`}
          className="grid grid-cols-[1fr_1fr_1fr_1fr] border-b border-white/[0.06] py-2 text-xs tabular-nums"
        >
          <span className="font-medium text-white">{row.symbol}</span>
          <span className="text-right text-ink">{fmtQty(row.current_volume)}</span>
          <span className="text-right text-muted">{fmtQty(row.baseline_mean)}</span>
          <span className={(row.z_score ?? 0) >= 3 ? "text-right text-gold" : "text-right text-buy"}>
            {row.z_score === null ? "—" : fmtPrice(row.z_score)}
          </span>
        </div>
      ))}
    </section>
  );
}
