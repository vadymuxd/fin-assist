import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ChevronDown } from "lucide-react";
import type { MortgageInsight } from "@/lib/queries";

function fmtDate(iso: string): string {
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

function fmtShort(iso: string): string {
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    timeZone: "UTC",
  });
}

function timeAgo(iso: string): string {
  const m = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.round(h / 24)}d ago`;
}

function Chip({
  label,
  value,
  wowBps,
}: {
  label: string;
  value: string;
  wowBps?: number | null;
}) {
  return (
    <span className="inline-flex items-baseline gap-1 rounded-md bg-gray-100 dark:bg-gray-800 px-2 py-1 text-[11px]">
      <span className="text-gray-500 dark:text-gray-400">{label}</span>
      <span className="font-semibold tabular-nums text-gray-900 dark:text-gray-50">{value}</span>
      {wowBps != null && <WowDelta bps={wowBps} />}
    </span>
  );
}

// Week-over-week change indicator: ↑ rising (amber), ↓ falling (green — cheaper
// borrowing is good for a remortgager), → flat (grey).
function WowDelta({ bps }: { bps: number }) {
  if (bps === 0) {
    return <span className="font-medium text-gray-400 dark:text-gray-500">→ flat</span>;
  }
  const up = bps > 0;
  const cls = up
    ? "text-amber-600 dark:text-amber-400"
    : "text-emerald-600 dark:text-emerald-400";
  return (
    <span className={`font-medium tabular-nums ${cls}`}>
      {up ? "↑" : "↓"} {up ? "+" : ""}
      {bps}bps
    </span>
  );
}

export default function InsightCard({
  insight,
  open,
}: {
  insight: MortgageInsight;
  open: boolean;
}) {
  const i = insight;

  return (
    <details
      open={open}
      className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 shadow-sm overflow-hidden"
    >
      <summary className="cursor-pointer list-none px-4 sm:px-6 py-4 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-semibold text-gray-900 dark:text-gray-50">
                {fmtDate(i.report_date)}
              </span>
              <span
                className={`text-[10px] font-medium uppercase tracking-wide px-1.5 py-0.5 rounded ${
                  i.triggered_by === "manual"
                    ? "bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300"
                    : "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400"
                }`}
              >
                {i.triggered_by === "manual" ? "Manual" : "Scheduled"}
              </span>
              <span className="text-xs text-gray-400 dark:text-gray-500">
                {timeAgo(i.created_at)}
              </span>
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {i.avg_2yr_rate != null && (
                <Chip
                  label="2yr avg"
                  value={`${i.avg_2yr_rate.toFixed(2)}%`}
                  wowBps={i.avg_2yr_wow_bps}
                />
              )}
              {i.avg_5yr_rate != null && (
                <Chip
                  label="5yr avg"
                  value={`${i.avg_5yr_rate.toFixed(2)}%`}
                  wowBps={i.avg_5yr_wow_bps}
                />
              )}
              {i.base_rate != null && (
                <Chip label="BoE base" value={`${i.base_rate.toFixed(2)}%`} />
              )}
              {i.next_mpc && <Chip label="Next MPC" value={fmtShort(i.next_mpc)} />}
            </div>
          </div>
          <ChevronDown
            size={18}
            strokeWidth={2}
            aria-hidden="true"
            className="insight-chevron shrink-0 mt-0.5 text-gray-400 dark:text-gray-500"
          />
        </div>
      </summary>
      <div className="border-t border-gray-200 dark:border-gray-800 px-4 sm:px-6 py-4 report-md">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{i.report_md}</ReactMarkdown>
      </div>
    </details>
  );
}
