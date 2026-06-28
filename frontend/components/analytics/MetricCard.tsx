export function MetricCard({
  label,
  value,
  detail,
  tone = "accent"
}: {
  label: string;
  value: string;
  detail: string;
  tone?: "accent" | "buy" | "sell" | "cyan" | "gold";
}) {
  const toneClass = {
    accent: "text-accent",
    buy: "text-buy",
    sell: "text-sell",
    cyan: "text-cyan",
    gold: "text-gold"
  }[tone];

  return (
    <section className="rounded-lg border border-line bg-[linear-gradient(135deg,rgba(255,255,255,0.07),rgba(255,255,255,0.025)),#15151c] p-4 shadow-2xl">
      <div className="text-xs uppercase text-muted">{label}</div>
      <div className={`mt-3 text-2xl font-semibold tabular-nums ${toneClass}`}>{value}</div>
      <div className="mt-2 text-xs text-muted">{detail}</div>
    </section>
  );
}
