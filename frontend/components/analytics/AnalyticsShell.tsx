import Link from "next/link";
import { Activity, BarChart3, ChevronLeft, Radar, ShieldCheck } from "lucide-react";

export function AnalyticsShell({ children }: { children: React.ReactNode }) {
  return (
    <main className="min-h-screen p-3 text-ink sm:p-5">
      <div className="mx-auto min-h-[calc(100vh-2.5rem)] max-w-[1500px] overflow-hidden rounded-[28px] border border-white/15 bg-black/35 shadow-[0_24px_90px_rgba(0,0,0,0.55)] backdrop-blur-xl">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 p-5">
          <div className="flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-lg bg-accent text-black">
              <Radar className="h-5 w-5" aria-hidden />
            </div>
            <div>
              <h1 className="text-2xl font-semibold text-white">Analytics Layer</h1>
              <div className="mt-1 flex items-center gap-2 text-sm text-muted">
                <ShieldCheck className="h-4 w-4 text-buy" aria-hidden />
                Read-only market intelligence
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Link
              href="/"
              className="inline-flex h-10 items-center gap-2 rounded-lg border border-white/10 bg-white/[0.06] px-3 text-sm text-muted hover:text-white"
            >
              <ChevronLeft className="h-4 w-4" aria-hidden />
              Dashboard
            </Link>
            <div className="hidden h-10 items-center gap-2 rounded-lg border border-white/10 bg-white/[0.06] px-3 text-sm text-muted md:flex">
              <BarChart3 className="h-4 w-4" aria-hidden />
              Trend, spread, volatility
            </div>
            <div className="hidden h-10 items-center gap-2 rounded-lg border border-white/10 bg-white/[0.06] px-3 text-sm text-buy md:flex">
              <Activity className="h-4 w-4" aria-hidden />
              Live
            </div>
          </div>
        </header>
        <section className="p-4 sm:p-5 lg:p-6">{children}</section>
      </div>
    </main>
  );
}
