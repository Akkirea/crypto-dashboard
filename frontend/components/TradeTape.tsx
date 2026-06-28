import { TradeEvent } from "@/lib/types";
import { fmtPrice, fmtQty, fmtTime } from "@/lib/format";

export function TradeTape({ trades }: { trades: TradeEvent[] }) {
  return (
    <section className="rounded-lg border border-line bg-panel/90 p-4 shadow-2xl">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ink">Trade Tape</h2>
        <span className="rounded-full border border-white/10 px-2 py-1 text-xs text-muted">{trades.length} latest</span>
      </div>
      <div className="grid grid-cols-[1fr_1fr_1fr] border-b border-line pb-2 text-xs font-medium text-muted">
        <span>Price</span>
        <span className="text-right">Qty</span>
        <span className="text-right">Time</span>
      </div>
      <div className="max-h-[420px] overflow-hidden">
        {trades.slice(0, 26).map((trade) => (
          <div
            key={trade.trade_id}
            className="grid grid-cols-[1fr_1fr_1fr] border-b border-white/[0.06] py-1.5 text-xs tabular-nums text-ink"
          >
            <span className={trade.buyer_maker ? "text-sell" : "text-buy"}>
              {fmtPrice(trade.price)}
            </span>
            <span className="text-right">{fmtQty(trade.quantity)}</span>
            <span className="text-right text-muted">{fmtTime(trade.trade_time)}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
