"use client";

import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import type { NetWorthPoint } from "@/lib/queries";

const gbp = new Intl.NumberFormat("en-GB", {
  style: "currency",
  currency: "GBP",
  maximumFractionDigits: 0,
});

const slices = [
  { key: "investments" as const, name: "Investments", color: "#2563eb" },
  { key: "savings" as const, name: "Savings", color: "#10b981" },
];

export default function NetWorthAllocationChart({ data }: { data: NetWorthPoint[] }) {
  if (data.length === 0) {
    return (
      <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4 sm:p-6 shadow-sm">
        <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50 mb-4">Allocation</h2>
        <div className="h-56 flex items-center justify-center text-sm text-gray-500 dark:text-gray-400 text-center px-4">
          No data yet.
        </div>
      </div>
    );
  }

  const sorted = [...data].sort((a, b) => a.date.localeCompare(b.date));
  const latest = sorted[sorted.length - 1];
  const total = latest.net_worth;

  const chartData = slices.map((s) => ({
    name: s.name,
    value: latest[s.key],
    pct: total > 0 ? (latest[s.key] / total) * 100 : 0,
    color: s.color,
  }));

  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4 sm:p-6 shadow-sm">
      <div className="mb-4">
        <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">Allocation</h2>
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">Savings vs investments</p>
      </div>

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
                paddingAngle={2}
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
            <div className="text-[10px] uppercase tracking-wide text-gray-400 dark:text-gray-500">Net Worth</div>
            <div className="text-base sm:text-lg font-semibold tabular-nums text-gray-900 dark:text-gray-50">
              {gbp.format(total)}
            </div>
          </div>
        </div>

        <div className="sm:col-span-3">
          <ul className="space-y-3">
            {chartData.map((d) => (
              <li key={d.name} className="flex items-center justify-between gap-3 text-sm">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ backgroundColor: d.color }} />
                  <span className="text-gray-700 dark:text-gray-300">{d.name}</span>
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
    </div>
  );
}
