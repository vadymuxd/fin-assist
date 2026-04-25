import type { Discovery } from "@/lib/queries";

function timeAgo(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const m = Math.round(ms / 60000);
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.round(h / 24);
  return `${d}d ago`;
}

function recBadge(rec: string | null): { label: string; className: string } {
  switch ((rec ?? "").toUpperCase()) {
    case "BUY":
      return { label: "BUY", className: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300" };
    case "WATCH":
      return { label: "WATCH", className: "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300" };
    case "SKIP":
      return { label: "SKIP", className: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400" };
    default:
      return { label: rec ?? "—", className: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400" };
  }
}

function scoreColor(score: number | null): string {
  if (score == null) return "text-gray-400";
  if (score >= 8) return "text-emerald-600 dark:text-emerald-400";
  if (score >= 6) return "text-amber-600 dark:text-amber-400";
  return "text-gray-500 dark:text-gray-400";
}

export default function DiscoveriesFeed({
  runTime,
  items,
}: {
  runTime: string;
  items: Discovery[];
}) {
  const surfaced = items.filter((i) => i.surfaced_to_telegram);
  const filtered = items.filter((i) => !i.surfaced_to_telegram);

  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 shadow-sm overflow-hidden">
      <div className="px-4 sm:px-6 py-4 border-b border-gray-200 dark:border-gray-800 flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">Today&apos;s Discoveries</h2>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
            {runTime ? `Latest run · ${timeAgo(runTime)}` : "No runs yet"}
          </p>
        </div>
        {items.length > 0 && (
          <span className="text-xs text-gray-500 dark:text-gray-400 tabular-nums">
            {surfaced.length} surfaced · {filtered.length} filtered
          </span>
        )}
      </div>

      {items.length === 0 ? (
        <div className="px-6 py-12 text-center text-sm text-gray-500 dark:text-gray-400">
          No discoveries yet. The discovery scanner runs daily and surfaces new tickers worth a look.
        </div>
      ) : (
        <ul className="divide-y divide-gray-100 dark:divide-gray-800">
          {[...surfaced, ...filtered].map((d) => {
            const muted = !d.surfaced_to_telegram;
            const badge = recBadge(d.recommendation);
            return (
              <li
                key={d.id}
                className={`px-4 sm:px-6 py-3 ${muted ? "opacity-60" : ""}`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-semibold text-gray-900 dark:text-gray-50">{d.ticker}</span>
                      <span className={`text-[10px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded ${badge.className}`}>
                        {badge.label}
                      </span>
                      {d.surfaced_to_telegram && (
                        <span className="text-[10px] font-medium uppercase tracking-wide px-1.5 py-0.5 rounded bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300">
                          ✈ Telegram
                        </span>
                      )}
                    </div>
                    {d.rationale ? (
                      <p className="mt-1 text-sm text-gray-600 dark:text-gray-300 line-clamp-2">{d.rationale}</p>
                    ) : d.filtered_reason ? (
                      <p className="mt-1 text-xs italic text-gray-500 dark:text-gray-400 line-clamp-1">Filtered: {d.filtered_reason}</p>
                    ) : null}
                    {d.sources && d.sources.length > 0 && (
                      <div className="mt-1.5 flex flex-wrap gap-1">
                        {d.sources.map((s) => (
                          <span
                            key={s}
                            className="text-[10px] text-gray-500 dark:text-gray-400 bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded"
                          >
                            {s}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="text-right shrink-0">
                    <div className={`text-2xl font-semibold tabular-nums ${scoreColor(d.score)}`}>
                      {d.score ?? "—"}
                    </div>
                    <div className="text-[10px] uppercase tracking-wide text-gray-400 dark:text-gray-500">
                      score
                    </div>
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
