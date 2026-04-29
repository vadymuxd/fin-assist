import Image from "next/image";
import type { NewsItem } from "@/lib/queries";

function dayKey(iso: string): string {
  return iso.slice(0, 10);
}

function dayLabel(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  const today = new Date();
  today.setUTCHours(0, 0, 0, 0);
  const diff = Math.round((today.getTime() - d.getTime()) / 86400000);
  if (diff === 0) return "Today";
  if (diff === 1) return "Yesterday";
  return d.toLocaleDateString("en-GB", { weekday: "short", day: "2-digit", month: "short", timeZone: "UTC" });
}

function timeOnly(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

function sentimentDot(s: string | null) {
  if (s === "bullish") return "bg-emerald-500";
  if (s === "bearish") return "bg-rose-500";
  return "bg-gray-300 dark:bg-gray-600";
}

function isValidUrl(s: string | null | undefined): s is string {
  if (!s) return false;
  return s.startsWith("http://") || s.startsWith("https://");
}

function groupByDay(items: NewsItem[]): { day: string; items: NewsItem[] }[] {
  const groups: Record<string, NewsItem[]> = {};
  for (const n of items) {
    if (!n.published_at) continue;
    const k = dayKey(n.published_at);
    (groups[k] ??= []).push(n);
  }
  return Object.entries(groups)
    .sort(([a], [b]) => b.localeCompare(a))
    .map(([day, items]) => ({ day, items }));
}

export default function NewsStream({ items }: { items: NewsItem[] }) {
  const groups = groupByDay(items);

  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 shadow-sm overflow-hidden">
      <div className="px-4 sm:px-6 py-4 border-b border-gray-200 dark:border-gray-800">
        <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">News Stream</h2>
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
          {items.length === 0 ? "No items yet" : `${items.length} recent item${items.length === 1 ? "" : "s"}`}
        </p>
      </div>

      {groups.length === 0 ? (
        <div className="px-6 py-12 text-center text-sm text-gray-500 dark:text-gray-400">
          No news ingested yet.
        </div>
      ) : (
        <div>
          {groups.map(({ day, items }) => (
            <div key={day}>
              <div className="px-4 sm:px-6 py-2 bg-gray-50 dark:bg-gray-950/40 border-y border-gray-100 dark:border-gray-800 text-[11px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                {dayLabel(day)}
              </div>
              <ul className="divide-y divide-gray-100 dark:divide-gray-800">
                {items.map((n) => {
                  const hasLink = isValidUrl(n.url);
                  const Wrapper = hasLink ? "a" : "div";
                  const wrapperProps = hasLink
                    ? { href: n.url!, target: "_blank", rel: "noopener noreferrer" }
                    : {};
                  return (
                  <li key={n.id} className="px-4 sm:px-6 py-3">
                    <Wrapper
                      {...wrapperProps}
                      className={`flex gap-3 ${hasLink ? "group" : ""}`}
                    >
                      {isValidUrl(n.image_url) ? (
                        <div className="shrink-0 w-16 h-16 rounded-md overflow-hidden bg-gray-100 dark:bg-gray-800 relative">
                          <Image
                            src={n.image_url!}
                            alt=""
                            fill
                            unoptimized
                            sizes="64px"
                            className="object-cover"
                          />
                        </div>
                      ) : (
                        <div className="shrink-0 w-16 h-16 rounded-md bg-gradient-to-br from-gray-100 to-gray-200 dark:from-gray-800 dark:to-gray-900" />
                      )}
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1.5 text-[10px] text-gray-500 dark:text-gray-400">
                          <span className={`w-1.5 h-1.5 rounded-full ${sentimentDot(n.sentiment)}`} />
                          {n.source && <span className="font-medium uppercase tracking-wide">{n.source}</span>}
                          {n.published_at && <span>· {timeOnly(n.published_at)}</span>}
                        </div>
                        <h3 className="mt-0.5 text-sm font-medium text-gray-900 dark:text-gray-50 line-clamp-2 group-hover:underline">
                          {n.title ?? "(untitled)"}
                        </h3>
                        {n.snippet && (
                          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400 line-clamp-2">{n.snippet}</p>
                        )}
                        {n.tickers && n.tickers.length > 0 && (
                          <div className="mt-1.5 flex flex-wrap gap-1">
                            {n.tickers.slice(0, 5).map((t) => (
                              <span
                                key={t}
                                className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400"
                              >
                                {t}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    </Wrapper>
                  </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
