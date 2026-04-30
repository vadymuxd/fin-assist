import Link from "next/link";
import type { HoldingsAlert } from "@/lib/queries";

function timeAgo(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const m = Math.round(ms / 60000);
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.round(h / 24);
  return `${d}d ago`;
}

function actionBadge(action: string | null, level: string): { label: string; dot: string; pill: string } {
  // Prefer suggested_action (SELL / TRIM / EXIT / BUY MORE) — the actual recommendation.
  // Fall back to alert_level when suggested_action is missing (legacy bot rows).
  const a = (action ?? "").toUpperCase();
  if (a === "SELL" || a === "EXIT") {
    return {
      label: a,
      dot: "bg-rose-500",
      pill: "bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300",
    };
  }
  if (a === "TRIM") {
    return {
      label: "TRIM",
      dot: "bg-orange-500",
      pill: "bg-orange-100 text-orange-700 dark:bg-orange-500/15 dark:text-orange-300",
    };
  }
  if (a === "BUY_MORE" || a === "BUY") {
    return {
      label: "BUY MORE",
      dot: "bg-emerald-500",
      pill: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300",
    };
  }
  return {
    label: a || "—",
    dot: "bg-gray-300 dark:bg-gray-600",
    pill: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
  };
}

export default function AlertsList({
  active,
  latestRun,
}: {
  active: HoldingsAlert[];
  latestRun: { run_time: string; items: HoldingsAlert[] };
}) {
  const hasActive = active.length > 0;

  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 shadow-sm overflow-hidden">
      <div className="px-4 sm:px-6 py-4 border-b border-gray-200 dark:border-gray-800 flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">Holdings Alerts</h2>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
            {latestRun.run_time ? `Last checked · ${timeAgo(latestRun.run_time)}` : "No runs yet"}
          </p>
        </div>
        {hasActive && (
          <span className="text-xs font-semibold text-rose-600 dark:text-rose-400 tabular-nums">
            {active.length} active
          </span>
        )}
      </div>

      {!hasActive ? (
        <div className="px-6 py-10 text-center">
          <div className="inline-flex items-center justify-center w-10 h-10 rounded-full bg-emerald-100 dark:bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 text-xl mb-2">
            ✓
          </div>
          <div className="text-sm font-medium text-gray-900 dark:text-gray-50">No actionable alerts</div>
          <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
            No concrete sell or buy signals detected in the last 7 days.
          </div>
        </div>
      ) : (
        <ul className="divide-y divide-gray-100 dark:divide-gray-800">
          {active.map((a) => {
            const badge = actionBadge(a.suggested_action, a.alert_level);
            return (
              <li key={a.id} className="px-4 sm:px-6 py-3">
                <Link
                  href={`/holdings/${encodeURIComponent(a.ticker)}`}
                  className="flex items-start gap-3 group"
                >
                  <span className={`mt-1.5 w-2 h-2 rounded-full shrink-0 ${badge.dot}`} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-semibold text-gray-900 dark:text-gray-50 group-hover:underline">
                        {a.ticker}
                      </span>
                      <span className={`text-[10px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded ${badge.pill}`}>
                        {badge.label}
                      </span>
                      <span className="text-xs text-gray-400 dark:text-gray-500 ml-auto">
                        {timeAgo(a.run_time)}
                      </span>
                    </div>
                    {a.event && (
                      <div className="mt-1 text-sm font-medium text-gray-700 dark:text-gray-200">{a.event}</div>
                    )}
                    {a.rationale && (
                      <p className="mt-1 text-sm text-gray-600 dark:text-gray-300 line-clamp-3">{a.rationale}</p>
                    )}
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
