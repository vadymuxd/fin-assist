import type { NetWorthPoint } from "@/lib/queries";

const gbp = new Intl.NumberFormat("en-GB", {
  style: "currency",
  currency: "GBP",
  maximumFractionDigits: 0,
});

function fmtPct(pct: number) {
  return `${pct > 0 ? "+" : ""}${pct.toFixed(2)}%`;
}
function fmtAbs(abs: number) {
  return `${abs >= 0 ? "+" : "−"}${gbp.format(Math.abs(abs))}`;
}
function deltaColor(pct: number) {
  if (pct > 0) return "text-emerald-600 dark:text-emerald-400";
  if (pct < 0) return "text-rose-600 dark:text-rose-400";
  return "text-gray-500 dark:text-gray-400";
}
function deltaBg(pct: number) {
  if (pct > 0) return "bg-emerald-50 dark:bg-emerald-500/10";
  if (pct < 0) return "bg-rose-50 dark:bg-rose-500/10";
  return "bg-gray-50 dark:bg-gray-800";
}
function shortDate(iso: string) {
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-GB", {
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

type DeltaInfo = { absolute: number; pct: number; fromDate: string } | null;

function computeDelta(latest: number, prev: NetWorthPoint | null): DeltaInfo {
  if (!prev) return null;
  const absolute = latest - prev.net_worth;
  const pct = prev.net_worth === 0 ? 0 : (absolute / prev.net_worth) * 100;
  return { absolute, pct, fromDate: prev.date };
}

function daysAgoISO(days: number) {
  const d = new Date();
  d.setUTCHours(0, 0, 0, 0);
  d.setUTCDate(d.getUTCDate() - days);
  return d.toISOString().slice(0, 10);
}

function findOnOrBefore(points: NetWorthPoint[], target: string): NetWorthPoint | null {
  const c = points.filter((p) => p.date <= target);
  return c.length === 0 ? null : c[c.length - 1];
}

function DeltaCard({ label, delta }: { label: string; delta: DeltaInfo }) {
  return (
    <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-4 shadow-sm">
      <div className="flex items-center justify-between">
        <div className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">{label}</div>
        {delta && (
          <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${deltaBg(delta.pct)} ${deltaColor(delta.pct)}`}>
            {delta.pct >= 0 ? "▲" : "▼"}
          </span>
        )}
      </div>
      {delta ? (
        <>
          <div className={`mt-2 text-xl sm:text-2xl font-semibold tabular-nums ${deltaColor(delta.pct)}`}>
            {fmtPct(delta.pct)}
          </div>
          <div className={`mt-0.5 text-xs tabular-nums ${deltaColor(delta.pct)}`}>{fmtAbs(delta.absolute)}</div>
          <div className="mt-1 text-[10px] text-gray-400 dark:text-gray-500">since {shortDate(delta.fromDate)}</div>
        </>
      ) : (
        <div className="mt-2 text-xl sm:text-2xl font-semibold tabular-nums text-gray-300 dark:text-gray-700">—</div>
      )}
    </div>
  );
}

function BreakdownChip({ label, value, total, color }: { label: string; value: number; total: number; color: string }) {
  const pct = total > 0 ? (value / total) * 100 : 0;
  return (
    <div className="flex flex-col">
      <div className="flex items-center gap-1.5">
        <span className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
        <div className="text-[10px] uppercase tracking-wide text-gray-400 dark:text-gray-500">{label}</div>
      </div>
      <div className="text-sm font-medium tabular-nums text-gray-900 dark:text-gray-50 mt-0.5">{gbp.format(value)}</div>
      <div className="text-[10px] text-gray-400 dark:text-gray-500 tabular-nums">{pct.toFixed(0)}%</div>
    </div>
  );
}

export default function NetWorthKpiCards({ data }: { data: NetWorthPoint[] }) {
  if (data.length === 0) {
    return (
      <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-6 text-center text-sm text-gray-500 dark:text-gray-400">
        No net worth data yet — run savings and portfolio snapshots to populate.
      </div>
    );
  }

  const sorted = [...data].sort((a, b) => a.date.localeCompare(b.date));
  const latest = sorted[sorted.length - 1];
  const prior = sorted.slice(0, -1);

  const wow = computeDelta(latest.net_worth, findOnOrBefore(prior, daysAgoISO(7)));
  const mom = computeDelta(latest.net_worth, findOnOrBefore(prior, daysAgoISO(30)));
  const yearStart = `${new Date().getUTCFullYear()}-01-01`;
  const ytd = computeDelta(latest.net_worth, findOnOrBefore(prior, yearStart));

  return (
    <div className="space-y-3 sm:space-y-4">
      <div className="rounded-xl border border-violet-200 dark:border-violet-900/50 bg-gradient-to-br from-white to-violet-50/40 dark:from-gray-900 dark:to-violet-950/20 p-5 sm:p-6 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
          <div>
            <div className="text-xs font-medium uppercase tracking-wide text-violet-600 dark:text-violet-400">
              Net Worth
            </div>
            <div className="mt-1 text-3xl sm:text-4xl font-semibold tabular-nums text-gray-900 dark:text-gray-50">
              {gbp.format(latest.net_worth)}
            </div>
            <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              as of {shortDate(latest.date)}
            </div>
          </div>
          <div className="grid grid-cols-3 gap-4 sm:gap-6">
            <BreakdownChip label="Investments" value={latest.investments} total={latest.net_worth} color="#2563eb" />
            <BreakdownChip label="Savings" value={latest.savings} total={latest.net_worth} color="#10b981" />
            <BreakdownChip label="Pensions" value={latest.pensions} total={latest.net_worth} color="#f59e0b" />
          </div>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3 sm:gap-4">
        <DeltaCard label="WoW" delta={wow} />
        <DeltaCard label="MoM" delta={mom} />
        <DeltaCard label="YTD" delta={ytd} />
      </div>
    </div>
  );
}
