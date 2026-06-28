import { Wifi, WifiOff } from "lucide-react";
import { HealthEvent } from "@/lib/types";
import { fmtTime } from "@/lib/format";

export function ConnectionHealth({ health }: { health?: HealthEvent }) {
  const ok = health?.connected && health.status === "healthy";
  return (
    <section className="rounded-lg border border-line bg-panel/90 p-4 shadow-2xl">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ink">Connection</h2>
        {ok ? (
          <Wifi className="h-4 w-4 text-buy" aria-hidden />
        ) : (
          <WifiOff className="h-4 w-4 text-sell" aria-hidden />
        )}
      </div>
      <div className="mt-3 grid grid-cols-2 gap-3 text-sm">
        <div>
          <div className="text-muted">Status</div>
          <div className="font-medium capitalize text-ink">{health?.status ?? "connecting"}</div>
        </div>
        <div>
          <div className="text-muted">Reconnects</div>
          <div className="font-medium tabular-nums text-ink">{health?.reconnect_count ?? 0}</div>
        </div>
        <div>
          <div className="text-muted">Latency</div>
          <div className="font-medium tabular-nums text-ink">{health?.latency_ms ?? "—"} ms</div>
        </div>
        <div>
          <div className="text-muted">Last Msg</div>
          <div className="font-medium tabular-nums text-ink">{fmtTime(health?.last_message_at)}</div>
        </div>
      </div>
    </section>
  );
}
