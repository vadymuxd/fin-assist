import Link from "next/link";
import Image from "next/image";
import { notFound } from "next/navigation";
import {
  getHoldingByTicker,
  getHoldingPriceHistory,
  getLatestAlertForTicker,
  getNewsForTicker,
} from "@/lib/queries";
import TickerLogo from "@/app/components/ticker-logo";
import HoldingPriceChart from "@/app/components/holding-price-chart";

export const revalidate = 300;

const gbp = new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP", maximumFractionDigits: 0 });

function fmtPct(v: number | null | undefined) {
  if (v === null || v === undefined) return "—";
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toFixed(2)}%`;
}

function fmtAbs(v: number | null | undefined) {
  if (v === null || v === undefined) return "—";
  const sign = v >= 0 ? "+" : "−";
  return `${sign}${gbp.format(Math.abs(v))}`;
}

function pnlColor(v: number | null | undefined) {
  if (v === null || v === undefined) return "text-gray-500";
  if (v > 0) return "text-emerald-600 dark:text-emerald-400";
  if (v < 0) return "text-rose-600 dark:text-rose-400";
  return "text-gray-500 dark:text-gray-400";
}

function alertBadge(level: string) {
  const map: Record<string, string> = {
    ACT: "bg-rose-100 dark:bg-rose-950/50 text-rose-700 dark:text-rose-300",
    WATCH: "bg-amber-100 dark:bg-amber-950/50 text-amber-700 dark:text-amber-300",
    NONE: "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400",
  };
  return map[level] ?? map.NONE;
}

function sentimentBadge(s: string | null) {
  if (!s) return null;
  const map: Record<string, string> = {
    bullish: "bg-emerald-100 dark:bg-emerald-950/50 text-emerald-700 dark:text-emerald-300",
    bearish: "bg-rose-100 dark:bg-rose-950/50 text-rose-700 dark:text-rose-300",
    neutral: "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400",
  };
  const cls = map[s.toLowerCase()] ?? map.neutral;
  return (
    <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-medium ${cls}`}>{s}</span>
  );
}

export default async function HoldingDetailPage({
  params,
}: {
  params: Promise<{ ticker: string }>;
}) {
  const { ticker: rawTicker } = await params;
  const ticker = decodeURIComponent(rawTicker);

  const [holding, alert, news, priceHistory] = await Promise.all([
    getHoldingByTicker(ticker),
    getLatestAlertForTicker(ticker),
    getNewsForTicker(ticker, 10),
    getHoldingPriceHistory(ticker),
  ]);

  if (!holding) notFound();

  return (
    <div className="space-y-4 sm:space-y-6">
      <div>
        <Link href="/" className="text-xs text-gray-500 dark:text-gray-400 hover:underline">
          ← Back to Dashboard
        </Link>
      </div>

      {/* Header */}
      <div className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4 sm:p-6">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
          <div className="flex items-start gap-4">
            <TickerLogo ticker={holding.ticker} size={48} />
            <div>
            <h1 className="text-2xl font-semibold text-gray-900 dark:text-gray-50">{holding.ticker}</h1>
            {holding.name && <div className="text-sm text-gray-500 dark:text-gray-400">{holding.name}</div>}
            <div className="mt-2 flex flex-wrap gap-2 text-xs">
              {holding.platform && (
                <span className="px-2 py-0.5 rounded-full bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300">
                  {holding.platform}
                </span>
              )}
              {holding.sector && (
                <span className="px-2 py-0.5 rounded-full bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300">
                  {holding.sector}
                </span>
              )}
              {holding.market && (
                <span className="px-2 py-0.5 rounded-full bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300">
                  {holding.market}
                </span>
              )}
            </div>
            </div>
          </div>
          <div className="text-right">
            <div className="text-2xl font-semibold tabular-nums text-gray-900 dark:text-gray-50">
              {holding.value_gbp !== null ? gbp.format(holding.value_gbp) : "—"}
            </div>
            <div className={`text-sm tabular-nums ${pnlColor(holding.pnl_pct)}`}>
              {fmtAbs(holding.pnl_abs)} ({fmtPct(holding.pnl_pct)})
            </div>
          </div>
        </div>

        <dl className="mt-6 grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
          <div>
            <dt className="text-xs uppercase tracking-wide text-gray-500 dark:text-gray-400">Qty</dt>
            <dd className="mt-1 tabular-nums text-gray-900 dark:text-gray-50">{holding.qty?.toLocaleString() ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-gray-500 dark:text-gray-400">Avg Buy</dt>
            <dd className="mt-1 tabular-nums text-gray-900 dark:text-gray-50">{holding.avg_buy?.toFixed(2) ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-gray-500 dark:text-gray-400">Current Price</dt>
            <dd className="mt-1 tabular-nums text-gray-900 dark:text-gray-50">
              {holding.current_price?.toFixed(2) ?? "—"}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-gray-500 dark:text-gray-400">Last Updated</dt>
            <dd className="mt-1 text-gray-900 dark:text-gray-50 text-xs">
              {holding.last_updated ? new Date(holding.last_updated).toLocaleString("en-GB") : "—"}
            </dd>
          </div>
        </dl>
      </div>

      {/* Price return chart */}
      <div className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4 sm:p-6">
        <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-50 mb-3">Return vs Cost Basis</h2>
        <HoldingPriceChart
          history={priceHistory}
          avgBuy={holding.avg_buy}
          ticker={holding.ticker}
        />
      </div>

      {/* Latest alert / score */}
      {alert && (
        <div className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4 sm:p-6">
          <div className="flex items-center gap-2 mb-3">
            <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-50">Latest Alert</h2>
            <span className={`px-2 py-0.5 rounded text-xs font-medium ${alertBadge(alert.alert_level)}`}>
              {alert.alert_level}
            </span>
            {alert.score !== null && (
              <span className="text-xs text-gray-500 dark:text-gray-400 tabular-nums">Score: {alert.score}</span>
            )}
            <span className="ml-auto text-xs text-gray-400 dark:text-gray-500">
              {new Date(alert.run_time).toLocaleString("en-GB")}
            </span>
          </div>
          {alert.event && (
            <div className="text-sm font-medium text-gray-900 dark:text-gray-50 mb-1">{alert.event}</div>
          )}
          {alert.rationale && (
            <p className="text-sm text-gray-600 dark:text-gray-300 whitespace-pre-wrap">{alert.rationale}</p>
          )}
        </div>
      )}

      {/* Recent news */}
      <div className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 overflow-hidden">
        <div className="px-4 sm:px-6 py-4 border-b border-gray-200 dark:border-gray-800">
          <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-50">Recent News</h2>
        </div>
        {news.length === 0 ? (
          <div className="p-6 text-center text-sm text-gray-500 dark:text-gray-400">
            No news for this ticker yet.
          </div>
        ) : (
          <ul className="divide-y divide-gray-100 dark:divide-gray-800">
            {news.map((n) => (
              <li key={n.id} className="p-4 sm:px-6 flex gap-3 sm:gap-4">
                {n.image_url ? (
                  <div className="relative w-16 h-16 sm:w-20 sm:h-20 rounded-md overflow-hidden bg-gray-100 dark:bg-gray-800 shrink-0">
                    <Image
                      src={n.image_url}
                      alt=""
                      fill
                      className="object-cover"
                      sizes="80px"
                      unoptimized
                    />
                  </div>
                ) : (
                  <div className="w-16 h-16 sm:w-20 sm:h-20 rounded-md bg-gray-100 dark:bg-gray-800 shrink-0" />
                )}
                <div className="min-w-0 flex-1">
                  <a
                    href={n.url ?? "#"}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block font-medium text-sm text-gray-900 dark:text-gray-50 hover:underline"
                  >
                    {n.title}
                  </a>
                  {n.snippet && (
                    <p className="mt-1 text-xs text-gray-600 dark:text-gray-400 line-clamp-2">{n.snippet}</p>
                  )}
                  <div className="mt-2 flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                    {n.source && <span>{n.source}</span>}
                    {n.published_at && <span>· {new Date(n.published_at).toLocaleDateString("en-GB")}</span>}
                    {sentimentBadge(n.sentiment)}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
