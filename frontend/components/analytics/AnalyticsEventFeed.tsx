import { AnalyticsEvent } from "@/lib/analyticsTypes";
import { fmtPrice, fmtTime } from "@/lib/format";

const severityClass: Record<string, string> = {
  info: "border-cyan/20 bg-cyan/10 text-cyan",
  warning: "border-gold/20 bg-gold/10 text-gold",
  critical: "border-sell/20 bg-sell/10 text-sell"
};

function eventTime(value: number | string) {
  if (typeof value === "number") return fmtTime(value);
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? "—" : fmtTime(parsed);
}

export function AnalyticsEventFeed({ events }: { events: AnalyticsEvent[] }) {
  return (
    <section className="rounded-lg border border-line bg-panel/90 p-4 shadow-2xl">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ink">Analytics Events</h2>
        <span className="rounded-full border border-white/10 px-2 py-1 text-xs text-muted">
          {events.length} recent
        </span>
      </div>
      <div className="space-y-2">
        {events.length === 0 ? (
          <div className="rounded-lg border border-white/10 bg-white/[0.035] p-3 text-sm text-muted">
            No analytics events emitted yet.
          </div>
        ) : null}
        {events.slice(0, 8).map((event, index) => (
          <div
            key={`${event.event_type}-${event.symbol}-${event.occurred_at}-${index}`}
            className="rounded-lg border border-white/10 bg-white/[0.035] p-3"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-sm font-medium text-white">
                  {event.symbol} · {event.event_type.replaceAll("_", " ")}
                </div>
                <div className="mt-1 text-xs text-muted">
                  {event.metric_name}: {fmtPrice(event.metric_value)}
                  {event.window ? ` · ${event.window}` : ""}
                </div>
              </div>
              <span className={`rounded-full border px-2 py-1 text-xs capitalize ${severityClass[event.severity]}`}>
                {event.severity}
              </span>
            </div>
            <div className="mt-2 text-xs text-muted">{eventTime(event.occurred_at)}</div>
          </div>
        ))}
      </div>
    </section>
  );
}
