import { Database, HardDrive, History, TimerReset } from "lucide-react";
import { AnalyticsStorageSummary, DatabaseHealth } from "@/lib/analyticsTypes";
import { fmtBytes, fmtCompact } from "@/lib/format";

function pct(value: number, total: number) {
  if (!total) return "0%";
  return `${Math.round((value / total) * 100)}%`;
}

function formatDate(value?: string) {
  if (!value) return "—";
  return new Date(value).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  });
}

export function StorageOpsPanel({
  health,
  storage
}: {
  health: DatabaseHealth | null;
  storage: AnalyticsStorageSummary | null;
}) {
  const tables = storage?.tables ?? health?.tables ?? [];
  const totalBytes = tables.reduce((sum, table) => sum + table.total_bytes, 0);
  const largest = tables[0];
  const rollups = storage?.rollups ?? [];

  return (
    <section className="rounded-lg border border-line bg-panel/90 p-4 shadow-2xl">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-ink">Storage Operations</h2>
          <div className="mt-1 text-xs text-muted">
            Retention, table growth, and rollup coverage
          </div>
        </div>
        <span className="inline-flex items-center gap-2 rounded-full border border-white/10 px-2 py-1 text-xs text-buy">
          <Database className="h-3.5 w-3.5" aria-hidden />
          {health?.connected ? "Postgres connected" : "Postgres pending"}
        </span>
      </div>

      <div className="grid gap-3 md:grid-cols-4">
        <div className="rounded-lg border border-white/10 bg-white/[0.04] p-3">
          <div className="flex items-center gap-2 text-xs text-muted">
            <HardDrive className="h-4 w-4 text-accent" aria-hidden />
            Total storage
          </div>
          <div className="mt-2 text-xl font-semibold tabular-nums text-white">{fmtBytes(totalBytes)}</div>
        </div>
        <div className="rounded-lg border border-white/10 bg-white/[0.04] p-3">
          <div className="flex items-center gap-2 text-xs text-muted">
            <History className="h-4 w-4 text-gold" aria-hidden />
            Largest table
          </div>
          <div className="mt-2 truncate text-xl font-semibold text-white">{largest?.table_name ?? "—"}</div>
          <div className="mt-1 text-xs text-muted">{fmtBytes(largest?.total_bytes)}</div>
        </div>
        <div className="rounded-lg border border-white/10 bg-white/[0.04] p-3">
          <div className="flex items-center gap-2 text-xs text-muted">
            <TimerReset className="h-4 w-4 text-buy" aria-hidden />
            Retention loop
          </div>
          <div className="mt-2 text-xl font-semibold tabular-nums text-white">
            {health ? `${Math.round(health.retention.interval_seconds / 60)}m` : "—"}
          </div>
          <div className="mt-1 text-xs text-muted">
            Delete cap {fmtCompact(health?.retention.delete_limit)}
          </div>
        </div>
        <div className="rounded-lg border border-white/10 bg-white/[0.04] p-3">
          <div className="flex items-center gap-2 text-xs text-muted">
            <TimerReset className="h-4 w-4 text-accent" aria-hidden />
            Rollup loop
          </div>
          <div className="mt-2 text-xl font-semibold tabular-nums text-white">
            {health ? `${Math.round(health.retention.rollups.interval_seconds / 60)}m` : "—"}
          </div>
          <div className="mt-1 text-xs text-muted">
            {health?.retention.rollups.order_book_bucket_minutes ?? "—"}m buckets
          </div>
        </div>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(360px,0.8fr)]">
        <div>
          <div className="grid grid-cols-[1fr_90px_90px_56px] border-b border-line pb-2 text-xs text-muted">
            <span>Table</span>
            <span className="text-right">Rows</span>
            <span className="text-right">Size</span>
            <span className="text-right">Share</span>
          </div>
          {tables.map((table) => (
            <div
              key={table.table_name}
              className="grid grid-cols-[1fr_90px_90px_56px] border-b border-white/[0.06] py-2 text-sm tabular-nums"
            >
              <span className="truncate font-medium text-white">{table.table_name}</span>
              <span className="text-right text-muted">{fmtCompact(table.estimated_rows)}</span>
              <span className="text-right text-ink">{fmtBytes(table.total_bytes)}</span>
              <span className="text-right text-muted">{pct(table.total_bytes, totalBytes)}</span>
            </div>
          ))}
        </div>

        <div>
          <div className="grid grid-cols-[1fr_78px_1fr] border-b border-line pb-2 text-xs text-muted">
            <span>Rollup</span>
            <span className="text-right">Buckets</span>
            <span className="text-right">Latest</span>
          </div>
          {rollups.length ? (
            rollups.map((rollup) => (
              <div
                key={`${rollup.exchange}-${rollup.symbol}-${rollup.bucket_minutes}`}
                className="grid grid-cols-[1fr_78px_1fr] border-b border-white/[0.06] py-2 text-sm tabular-nums"
              >
                <span className="truncate font-medium text-white">
                  {rollup.exchange} · {rollup.symbol}
                </span>
                <span className="text-right text-buy">{fmtCompact(rollup.bucket_count)}</span>
                <span className="text-right text-muted">{formatDate(rollup.last_bucket)}</span>
              </div>
            ))
          ) : (
            <div className="py-5 text-sm text-muted">Waiting for the first rollup pass.</div>
          )}
        </div>
      </div>
    </section>
  );
}
