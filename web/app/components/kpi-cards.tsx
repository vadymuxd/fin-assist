import type { DashboardDeltas } from "@/lib/queries";

const gbp = new Intl.NumberFormat("en-GB", {
  style: "currency",
  currency: "GBP",
  maximumFractionDigits: 0,
});

function formatPct(pct: number): string {
  const sign = pct > 0 ? "+" : "";
  return `${sign}${pct.toFixed(2)}%`;
}

function formatAbs(abs: number): string {
  const sign = abs >= 0 ? "+" : "−";
  return `${sign}${gbp.format(Math.abs(abs))}`;
}

function deltaColor(pct: number): string {
  if (pct > 0) return "text-emerald-600 dark:text-emerald-400";
  if (pct < 0) return "text-rose-600 dark:text-rose-400";
  return "text-gray-500 dark:text-gray-400";
}

type DeltaProps = {
  label: string;
  delta: { absolute: number; pct: number; fromDate: string } | null;
  fallbackLabel?: string;
};

function DeltaCard({ label, delta, fallbackLabel }: DeltaProps) {
  return (
    <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 p-4 sm:p-5">
      <div className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
        {label}
      </div>
      {delta ? (
        <>
          <div className={`mt-2 text-2xl sm:text-3xl font-semibold tabular-nums ${deltaColor(delta.pct)}`}>
            {formatPct(delta.pct)}
          </div>
          <div className={`mt-1 text-sm tabular-nums ${deltaColor(delta.pct)}`}>
            {formatAbs(delta.absolute)}
          </div>
          <div className="mt-1 text-xs text-gray-400 dark:text-gray-500">
            since {delta.fromDate}
          </div>
        </>
      ) : (
        <>
          <div className="mt-2 text-2xl sm:text-3xl font-semibold tabular-nums text-gray-400 dark:text-gray-600">
            —
          </div>
          <div className="mt-1 text-xs text-gray-400 dark:text-gray-500">
            {fallbackLabel ?? "Not enough history"}
          </div>
        </>
      )}
    </div>
  );
}

export default function KpiCards({ deltas }: { deltas: DashboardDeltas | null }) {
  if (!deltas) {
    return (
      <div className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-6 text-center text-sm text-gray-500 dark:text-gray-400">
        No portfolio snapshots yet.
      </div>
    );
  }

  const { latest, sinceBaseline, wow, mom, ytd } = deltas;

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 sm:gap-4">
      <div className="col-span-2 sm:col-span-1 bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 p-4 sm:p-5">
        <div className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
          Grand Total
        </div>
        <div className="mt-2 text-2xl sm:text-3xl font-semibold tabular-nums text-gray-900 dark:text-gray-50">
          {gbp.format(latest.grand_total)}
        </div>
        <div className="mt-1 text-xs text-gray-400 dark:text-gray-500">as of {latest.date}</div>
      </div>

      <DeltaCard label="WoW" delta={wow} fallbackLabel={sinceBaseline ? `Since ${sinceBaseline.fromDate}` : undefined} />
      <DeltaCard label="MoM" delta={mom} fallbackLabel={sinceBaseline ? `Since ${sinceBaseline.fromDate}` : undefined} />
      <DeltaCard label="YTD" delta={ytd} fallbackLabel={sinceBaseline ? `Since ${sinceBaseline.fromDate}` : undefined} />
    </div>
  );
}
