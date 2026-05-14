"use client";

import { useMemo, useState } from "react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import type { PensionAccount } from "@/lib/queries";

type Dimension   = "provider" | "account_name";
type OwnerFilter = "All" | "Vadym" | "Lisa";

const dimensionLabels: Record<Dimension, string> = {
  provider: "Provider",
  account_name: "Account",
};

const palette = [
  "#f59e0b", // amber
  "#6366f1", // indigo
  "#10b981", // emerald
  "#ef4444", // rose
  "#8b5cf6", // violet
  "#06b6d4", // cyan
  "#f97316", // orange
  "#ec4899", // pink
  "#84cc16", // lime
  "#3b82f6", // blue
];

const gbp = new Intl.NumberFormat("en-GB", {
  style: "currency",
  currency: "GBP",
  maximumFractionDigits: 0,
});

type Slice = { name: string; value: number; pct: number; color: string };

function bucket(accounts: PensionAccount[], dim: Dimension, ownerFilter: OwnerFilter): Slice[] {
  const filtered = ownerFilter === "All"
    ? accounts
    : accounts.filter((a) => (a.owner ?? "vadym").toLowerCase() === ownerFilter.toLowerCase());
  const totals: Record<string, number> = {};
  for (const a of filtered) {
    const key = dim === "provider" ? a.provider : a.account_name;
    const v = Number(a.balance_gbp ?? 0);
    if (!Number.isFinite(v) || v <= 0) continue;
    totals[key] = (totals[key] ?? 0) + v;
  }
  const total = Object.values(totals).reduce((a, b) => a + b, 0);
  return Object.entries(totals)
    .sort(([, a], [, b]) => b - a)
    .map(([name, value], i) => ({
      name,
      value,
      pct: total > 0 ? (value / total) * 100 : 0,
      color: palette[i % palette.length],
    }));
}

export default function PensionAllocationChart({ accounts }: { accounts: PensionAccount[] }) {
  const [dim, setDim]               = useState<Dimension>("provider");
  const [ownerFilter, setOwnerFilter] = useState<OwnerFilter>("All");

  const chartData = useMemo(() => bucket(accounts, dim, ownerFilter), [accounts, dim, ownerFilter]);
  const total = useMemo(() => chartData.reduce((acc, d) => acc + d.value, 0), [chartData]);
  const hasData = chartData.length > 0 && total > 0;

  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4 sm:p-6 shadow-sm">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
        <div>
          <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">Pension Allocation</h2>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
            {ownerFilter === "All" ? "All" : ownerFilter} balances by {dimensionLabels[dim].toLowerCase()}
          </p>
        </div>
        <div className="flex items-center gap-2 self-start">
          {/* Left toggle: Provider / Account */}
          <div className="flex items-center gap-0.5 bg-gray-100 dark:bg-gray-800 rounded-md p-0.5">
            {(Object.keys(dimensionLabels) as Dimension[]).map((d) => (
              <button
                key={d}
                onClick={() => setDim(d)}
                className={`px-2.5 py-1 text-xs font-medium rounded transition-colors ${
                  dim === d
                    ? "bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-50 shadow-sm"
                    : "text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-50"
                }`}
              >
                {dimensionLabels[d]}
              </button>
            ))}
          </div>
          {/* Right toggle: All / Vadym / Lisa */}
          <div className="flex items-center gap-0.5 bg-gray-100 dark:bg-gray-800 rounded-md p-0.5">
            {(["All", "Vadym", "Lisa"] as OwnerFilter[]).map((o) => (
              <button
                key={o}
                onClick={() => setOwnerFilter(o)}
                className={`px-2.5 py-1 text-xs font-medium rounded transition-colors ${
                  ownerFilter === o
                    ? "bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-50 shadow-sm"
                    : "text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-50"
                }`}
              >
                {o}
              </button>
            ))}
          </div>
        </div>
      </div>

      {!hasData ? (
        <div className="h-56 flex items-center justify-center text-sm text-gray-500 dark:text-gray-400 text-center px-4">
          No pension data yet.
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-5 gap-4 items-center">
          <div className="sm:col-span-2 relative h-56">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={chartData}
                  dataKey="value"
                  nameKey="name"
                  innerRadius="60%"
                  outerRadius="92%"
                  stroke="none"
                  paddingAngle={1.5}
                  isAnimationActive={false}
                >
                  {chartData.map((d) => (
                    <Cell key={d.name} fill={d.color} />
                  ))}
                </Pie>
                <Tooltip
                  formatter={(v) => [gbp.format(Number(v)), ""]}
                  contentStyle={{
                    background: "rgba(255,255,255,0.95)",
                    border: "1px solid #e5e7eb",
                    borderRadius: 8,
                    fontSize: 12,
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
              <div className="text-[10px] uppercase tracking-wide text-gray-400 dark:text-gray-500">Total</div>
              <div className="text-base sm:text-lg font-semibold tabular-nums text-gray-900 dark:text-gray-50">
                {gbp.format(total)}
              </div>
            </div>
          </div>
          <div className="sm:col-span-3">
            <ul className="space-y-1.5 max-h-56 overflow-y-auto pr-1">
              {chartData.map((d) => (
                <li key={d.name} className="flex items-center justify-between gap-3 text-sm">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ backgroundColor: d.color }} />
                    <span className="truncate text-gray-700 dark:text-gray-300 capitalize">{d.name}</span>
                  </div>
                  <div className="flex items-center gap-3 shrink-0 tabular-nums">
                    <span className="text-gray-500 dark:text-gray-400 w-12 text-right">{d.pct.toFixed(1)}%</span>
                    <span className="text-gray-900 dark:text-gray-50 font-medium w-20 text-right">{gbp.format(d.value)}</span>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}
