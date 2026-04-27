import type { PensionDelta, PensionDeltasResult } from "@/lib/queries";

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

function DeltaCard({ label, delta }: { label: string; delta: PensionDelta | null }) {
  return (
    <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-4 shadow-sm">
      <div className="flex items-center justify-between">
        <div className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
          {label}
        </div>
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
          <div className={`mt-0.5 text-xs tabular-nums ${deltaColor(delta.pct)}`}>
            {fmtAbs(delta.absolute)}
          </div>
          <div className="mt-1 text-[10px] text-gray-400 dark:text-gray-500">
            since {shortDate(delta.fromDate)}
          </div>
        </>
      ) : (
        <div className="mt-2 text-xl sm:text-2xl font-semibold tabular-nums text-gray-300 dark:text-gray-700">—</div>
      )}
    </div>
  );
}

export default function PensionKpiCards({ deltas }: { deltas: PensionDeltasResult | null }) {
  if (!deltas) {
    return (
      <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-6 text-center text-sm text-gray-500 dark:text-gray-400">
        No pension snapshots yet. Run <code className="font-mono text-xs">pension_snapshot.py</code> to seed data.
      </div>
    );
  }

  const { latest, daily, wow, mom, ytd } = deltas;

  return (
    <div className="space-y-3 sm:space-y-4">
      <div className="rounded-xl border border-amber-200 dark:border-amber-900/50 bg-gradient-to-br from-white to-amber-50/40 dark:from-gray-900 dark:to-amber-950/20 p-5 sm:p-6 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
          <div>
            <div className="text-xs font-medium uppercase tracking-wide text-amber-600 dark:text-amber-400">
              Total Pension
            </div>
            <div className="mt-1 text-3xl sm:text-4xl font-semibold tabular-nums text-gray-900 dark:text-gray-50">
              {gbp.format(latest.total)}
            </div>
            <div className="mt-1 flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
              <span>as of {shortDate(latest.date)}</span>
              {daily && (
                <>
                  <span className="text-gray-300 dark:text-gray-700">•</span>
                  <span className={`font-medium tabular-nums ${deltaColor(daily.pct)}`}>
                    {daily.pct >= 0 ? "▲" : "▼"} {fmtAbs(daily.absolute)} ({fmtPct(daily.pct)})
                  </span>
                </>
              )}
            </div>
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
