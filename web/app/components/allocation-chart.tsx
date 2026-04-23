"use client";

import { useMemo, useState } from "react";
import { DonutChart } from "@tremor/react";
import type { Holding } from "@/lib/queries";

type Dimension = "sector" | "market" | "platform";

const dimensionLabels: Record<Dimension, string> = {
  sector: "Sector",
  market: "Market",
  platform: "Platform",
};

const gbp = new Intl.NumberFormat("en-GB", {
  style: "currency",
  currency: "GBP",
  maximumFractionDigits: 0,
});

function bucket(holdings: Holding[], dim: Dimension): Array<{ name: string; value: number }> {
  const totals: Record<string, number> = {};
  for (const h of holdings) {
    const key = (h[dim] as string | null) || "Unknown";
    const v = Number(h.value_gbp ?? 0);
    if (!Number.isFinite(v) || v <= 0) continue;
    totals[key] = (totals[key] ?? 0) + v;
  }
  return Object.entries(totals)
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value);
}

export default function AllocationChart({ holdings }: { holdings: Holding[] }) {
  const [dim, setDim] = useState<Dimension>("sector");

  const data = useMemo(() => bucket(holdings, dim), [holdings, dim]);
  const total = useMemo(() => data.reduce((acc, d) => acc + d.value, 0), [data]);
  const hasData = data.length > 0 && total > 0;

  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4 sm:p-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
        <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-50">Allocation</h2>
        <div className="flex items-center gap-1 bg-gray-100 dark:bg-gray-800 rounded-md p-0.5 self-start">
          {(Object.keys(dimensionLabels) as Dimension[]).map((d) => (
            <button
              key={d}
              onClick={() => setDim(d)}
              className={`px-3 py-1 text-xs font-medium rounded transition-colors ${
                dim === d
                  ? "bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-50 shadow-sm"
                  : "text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-50"
              }`}
            >
              {dimensionLabels[d]}
            </button>
          ))}
        </div>
      </div>

      {!hasData ? (
        <div className="h-56 flex items-center justify-center text-sm text-gray-500 dark:text-gray-400 text-center px-4">
          No value_gbp data yet — run <code className="mx-1 px-1.5 py-0.5 bg-gray-100 dark:bg-gray-800 rounded text-xs">sheets_updater.py</code> after applying the holdings migration.
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-5 gap-4 items-center">
          <div className="sm:col-span-2">
            <DonutChart
              className="h-56"
              data={data}
              category="value"
              index="name"
              valueFormatter={(v: number) => gbp.format(v)}
              colors={["blue", "emerald", "amber", "violet", "rose", "cyan", "indigo", "fuchsia", "teal", "orange"]}
              variant="donut"
            />
            <div className="mt-3 text-center text-xs text-gray-500 dark:text-gray-400">
              Total: <span className="font-semibold text-gray-900 dark:text-gray-50 tabular-nums">{gbp.format(total)}</span>
            </div>
          </div>
          <div className="sm:col-span-3">
            <ul className="space-y-1.5">
              {data.map((d, i) => {
                const colors = ["bg-blue-500", "bg-emerald-500", "bg-amber-500", "bg-violet-500", "bg-rose-500", "bg-cyan-500", "bg-indigo-500", "bg-fuchsia-500", "bg-teal-500", "bg-orange-500"];
                const pct = total > 0 ? (d.value / total) * 100 : 0;
                return (
                  <li key={d.name} className="flex items-center justify-between gap-3 text-sm">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className={`w-2.5 h-2.5 rounded-sm ${colors[i % colors.length]} shrink-0`} />
                      <span className="truncate text-gray-700 dark:text-gray-300">{d.name}</span>
                    </div>
                    <div className="flex items-center gap-3 shrink-0 tabular-nums">
                      <span className="text-gray-500 dark:text-gray-400">{pct.toFixed(1)}%</span>
                      <span className="text-gray-900 dark:text-gray-50 font-medium">{gbp.format(d.value)}</span>
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}
