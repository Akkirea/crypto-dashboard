import { LiquidityRow } from "@/lib/analyticsTypes";
import { fmtPrice, fmtQty, fmtTime } from "@/lib/format";

export function LiquidityMonitor({ rows }: { rows: LiquidityRow[] }) {
  return (
    <section className="rounded-lg border border-line bg-panel/90 p-4 shadow-2xl">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ink">Liquidity Monitor</h2>
        <span className="rounded-full border border-white/10 px-2 py-1 text-xs text-muted">
          Depth 20
        </span>
      </div>
      <div className="space-y-3">
        {rows.map((row) => {
          const depth25 = row.depth["25bps"];
          const imbalance = row.order_book_imbalance ?? 0;
          return (
            <div key={`${row.exchange}-${row.symbol}`} className="rounded-lg border border-white/10 bg-white/[0.035] p-3">
              <div className="mb-2 flex items-center justify-between gap-3">
                <div>
                  <div className="font-medium text-white">{row.symbol}</div>
                  <div className="text-xs text-muted">
                    25bps depth {fmtQty(depth25?.total_notional)} quote
                  </div>
                </div>
                <div className="text-right text-xs text-muted">{fmtTime(row.last_update_at)}</div>
              </div>
              <div className="grid grid-cols-3 gap-2 text-xs">
                <div className="rounded-md border border-white/10 bg-black/20 p-2">
                  <div className="text-muted">10bps</div>
                  <div className="mt-1 text-ink tabular-nums">{fmtQty(row.depth["10bps"]?.total_notional)}</div>
                </div>
                <div className="rounded-md border border-white/10 bg-black/20 p-2">
                  <div className="text-muted">25bps</div>
                  <div className="mt-1 text-ink tabular-nums">{fmtQty(depth25?.total_notional)}</div>
                </div>
                <div className="rounded-md border border-white/10 bg-black/20 p-2">
                  <div className="text-muted">50bps</div>
                  <div className="mt-1 text-ink tabular-nums">{fmtQty(row.depth["50bps"]?.total_notional)}</div>
                </div>
              </div>
              <div className="mt-3 flex items-center justify-between text-xs">
                <span className={imbalance >= 0 ? "text-buy" : "text-sell"}>
                  Imbalance {fmtPrice(imbalance * 100)}%
                </span>
                <span className={(row.collapse.drop_pct ?? 0) >= 50 ? "text-sell" : "text-muted"}>
                  Drop {fmtPrice(row.collapse.drop_pct)}%
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
