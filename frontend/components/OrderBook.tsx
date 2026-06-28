import { BookTopEvent } from "@/lib/types";
import { fmtPrice, fmtQty } from "@/lib/format";

export function OrderBook({ book }: { book?: BookTopEvent }) {
  return (
    <section className="rounded-lg border border-line bg-panel/90 p-4 shadow-2xl">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ink">Top Of Book</h2>
        <span className="rounded-full border border-white/10 px-2 py-1 text-xs text-muted">Binance</span>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-md border border-buy/20 bg-buy/10 p-3">
          <div className="text-xs uppercase text-buy/80">Best Bid</div>
          <div className="mt-1 text-lg font-semibold tabular-nums text-white">{fmtPrice(book?.bid_price)}</div>
          <div className="text-xs text-buy/80">Qty {fmtQty(book?.bid_quantity)}</div>
        </div>
        <div className="rounded-md border border-sell/20 bg-sell/10 p-3">
          <div className="text-xs uppercase text-sell/80">Best Ask</div>
          <div className="mt-1 text-lg font-semibold tabular-nums text-white">{fmtPrice(book?.ask_price)}</div>
          <div className="text-xs text-sell/80">Qty {fmtQty(book?.ask_quantity)}</div>
        </div>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
        <div>
          <div className="text-muted">Spread</div>
          <div className="font-medium tabular-nums text-ink">{fmtPrice(book?.spread)}</div>
        </div>
        <div>
          <div className="text-muted">Spread bps</div>
          <div className="font-medium tabular-nums text-ink">{fmtPrice(book?.spread_bps)}</div>
        </div>
      </div>
    </section>
  );
}
