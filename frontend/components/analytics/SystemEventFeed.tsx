import { ServerCog } from "lucide-react";
import { SystemEvent } from "@/lib/analyticsTypes";

function tone(severity: SystemEvent["severity"]) {
  if (severity === "critical" || severity === "error") return "border-sell/30 bg-sell/10 text-sell";
  if (severity === "warning") return "border-gold/30 bg-gold/10 text-gold";
  return "border-white/10 bg-white/[0.04] text-muted";
}

function formatTime(value: string) {
  return new Date(value).toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  });
}

export function SystemEventFeed({ events }: { events: SystemEvent[] }) {
  return (
    <section className="rounded-lg border border-line bg-panel/90 p-4 shadow-2xl">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-ink">System Events</h2>
          <div className="mt-1 text-xs text-muted">Workers, retention, rollups, and lifecycle</div>
        </div>
        <span className="inline-flex items-center gap-2 rounded-full border border-white/10 px-2 py-1 text-xs text-muted">
          <ServerCog className="h-3.5 w-3.5" aria-hidden />
          {events.length} latest
        </span>
      </div>

      <div className="space-y-2">
        {events.length ? (
          events.slice(0, 12).map((event, index) => (
            <div
              key={`${event.component}-${event.event_type}-${event.occurred_at}-${index}`}
              className={`rounded-lg border p-3 text-sm ${tone(event.severity)}`}
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="font-medium text-white">
                  {event.component} · {event.event_type.replaceAll("_", " ")}
                </div>
                <div className="text-xs tabular-nums text-muted">{formatTime(event.occurred_at)}</div>
              </div>
              <div className="mt-1 text-xs">
                {event.status ?? event.severity}
                {event.message ? ` · ${event.message}` : ""}
              </div>
            </div>
          ))
        ) : (
          <div className="rounded-lg border border-white/10 bg-white/[0.04] p-4 text-sm text-muted">
            Waiting for system events.
          </div>
        )}
      </div>
    </section>
  );
}
