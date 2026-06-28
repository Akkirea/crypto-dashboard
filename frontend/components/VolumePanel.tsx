import { CandleEvent } from "@/lib/types";
import { fmtQty } from "@/lib/format";

export function VolumePanel({ candle1m, candle5m }: { candle1m?: CandleEvent; candle5m?: CandleEvent }) {
  return (
    <section className="rounded-lg border border-line bg-panel/90 p-4 shadow-2xl">
      <h2 className="text-sm font-semibold text-ink">Volume</h2>
      <div className="mt-3 grid grid-cols-2 gap-3 text-sm">
        <div>
          <div className="text-muted">1m Base</div>
          <div className="font-medium tabular-nums text-ink">{fmtQty(candle1m?.volume)}</div>
        </div>
        <div>
          <div className="text-muted">5m Base</div>
          <div className="font-medium tabular-nums text-ink">{fmtQty(candle5m?.volume)}</div>
        </div>
        <div>
          <div className="text-muted">1m Trades</div>
          <div className="font-medium tabular-nums text-ink">{candle1m?.trade_count ?? "—"}</div>
        </div>
        <div>
          <div className="text-muted">5m Trades</div>
          <div className="font-medium tabular-nums text-ink">{candle5m?.trade_count ?? "—"}</div>
        </div>
      </div>
    </section>
  );
}
