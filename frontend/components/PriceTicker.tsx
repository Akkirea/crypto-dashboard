import { Activity, Bitcoin, CircleDollarSign, Zap } from "lucide-react";
import { BookTopEvent } from "@/lib/types";
import { fmtPrice } from "@/lib/format";

const iconBySymbol = {
  BTCUSDT: Bitcoin,
  ETHUSDT: CircleDollarSign,
  SOLUSDT: Zap
};

export function PriceTicker({
  symbol,
  price,
  book,
  selected,
  onSelect
}: {
  symbol: string;
  price?: number;
  book?: BookTopEvent;
  selected: boolean;
  onSelect: () => void;
}) {
  const Icon = iconBySymbol[symbol as keyof typeof iconBySymbol] ?? Activity;
  return (
    <button
      onClick={onSelect}
      className={`group relative h-32 overflow-hidden rounded-lg border p-4 text-left shadow-2xl transition ${
        selected
          ? "border-accent/70 bg-[linear-gradient(135deg,rgba(196,181,253,0.22),rgba(91,231,255,0.08)),#181722] ring-2 ring-accent/15"
          : "border-line bg-[linear-gradient(135deg,rgba(255,255,255,0.06),rgba(255,255,255,0.02)),#13131a] hover:border-accent/40"
      }`}
    >
      <div className="absolute right-0 top-0 h-24 w-24 translate-x-8 -translate-y-8 rounded-full bg-accent/10 blur-2xl transition group-hover:bg-cyan/10" />
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-2 text-sm font-semibold text-ink">
          <span className="grid h-8 w-8 place-items-center rounded-md border border-white/10 bg-white/5">
            <Icon className="h-4 w-4 text-accent" aria-hidden />
          </span>
          {symbol}
        </span>
        <Activity className="h-4 w-4 text-buy" aria-hidden />
      </div>
      <div className="mt-4 text-2xl font-semibold tabular-nums text-white">${fmtPrice(price)}</div>
      <div className="mt-2 truncate text-xs text-muted">
        Bid {fmtPrice(book?.bid_price)} / Ask {fmtPrice(book?.ask_price)}
      </div>
    </button>
  );
}
