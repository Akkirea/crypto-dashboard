import { CrossExchangeRow } from "@/lib/analyticsTypes";
import { fmtPrice, fmtTime } from "@/lib/format";

export function CrossExchangePanel({ rows }: { rows: CrossExchangeRow[] }) {
  return (
    <section className="rounded-lg border border-line bg-panel/90 p-4 shadow-2xl">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ink">Cross-Exchange</h2>
        <span className="rounded-full border border-white/10 px-2 py-1 text-xs text-muted">
          Public feeds
        </span>
      </div>
      <div className="space-y-3">
        {rows.map((row) => (
          <div key={row.symbol} className="rounded-lg border border-white/10 bg-white/[0.035] p-3">
            <div className="mb-2 flex items-center justify-between gap-3">
              <div>
                <div className="font-medium text-white">{row.symbol}</div>
                <div className="text-xs text-muted">
                  Dispersion {fmtPrice(row.price_dispersion_bps)} bps
                </div>
              </div>
              <div className="text-right text-xs text-muted">
                Lead{" "}
                <span className="font-medium text-accent">
                  {row.price_discovery_leader?.exchange ?? "—"}
                </span>
              </div>
            </div>

            <div className="grid grid-cols-[1fr_1fr_1fr_1fr] border-b border-line pb-2 text-xs text-muted">
              <span>Venue</span>
              <span className="text-right">Price</span>
              <span className="text-right">Spread</span>
              <span className="text-right">Seen</span>
            </div>
            {row.venues.map((venue) => (
              <div
                key={`${row.symbol}-${venue.exchange}`}
                className="grid grid-cols-[1fr_1fr_1fr_1fr] border-b border-white/[0.06] py-1.5 text-xs tabular-nums"
              >
                <span className={venue.stale ? "capitalize text-sell" : "capitalize text-white"}>
                  {venue.exchange}
                </span>
                <span className="text-right text-ink">{fmtPrice(venue.latest_price)}</span>
                <span className="text-right text-buy">{fmtPrice(venue.spread_bps)}</span>
                <span className="text-right text-muted">{fmtTime(venue.last_seen_at)}</span>
              </div>
            ))}
          </div>
        ))}
      </div>
    </section>
  );
}
