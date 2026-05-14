"use client";

import { useState } from "react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import type { NetWorthPoint } from "@/lib/queries";

type Owner = "Joint" | "Vadym" | "Lisa";
const OWNERS: Owner[] = ["Joint", "Vadym", "Lisa"];

const gbp = new Intl.NumberFormat("en-GB", {
  style: "currency",
  currency: "GBP",
  maximumFractionDigits: 0,
});

type Slice = { name: string; value: number; pct: number; color: string };

function getSlices(latest: NetWorthPoint, owner: Owner): Slice[] {
  const equityHalf = latest.mortgage_equity / 2;

  const raw =
    owner === "Vadym" ? [
      { name: "Investments",  value: latest.vadym_investments, color: "#2563eb" },
      { name: "Savings",      value: latest.vadym_savings,     color: "#10b981" },
      { name: "Pensions",     value: latest.vadym_pensions,    color: "#f59e0b" },
      { name: "Mortgage (½)", value: equityHalf,               color: "#f97316" },
    ]
    : owner === "Lisa" ? [
      { name: "Investments",  value: latest.lisa_investments,  color: "#2563eb" },
      { name: "Savings",      value: latest.lisa_savings,      color: "#10b981" },
      { name: "Pensions",     value: latest.lisa_pensions,     color: "#f59e0b" },
      { name: "Mortgage (½)", value: equityHalf,               color: "#f97316" },
    ]
    : [
      { name: "Investments",     value: latest.investments,     color: "#2563eb" },
      { name: "Savings",         value: latest.savings,         color: "#10b981" },
      { name: "Pensions",        value: latest.pensions,        color: "#f59e0b" },
      { name: "Mortgage Equity", value: latest.mortgage_equity, color: "#f97316" },
    ];

  const total = raw.reduce((s, d) => s + d.value, 0);
  return raw
    .filter((d) => d.value > 0)
    .map((d) => ({ ...d, pct: total > 0 ? (d.value / total) * 100 : 0 }));
}

export default function NetWorthAllocationChart({ data }: { data: NetWorthPoint[] }) {
  const [owner, setOwner] = useState<Owner>("Joint");

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
  const chartData = getSlices(latest, owner);
  const total = chartData.reduce((s, d) => s + d.value, 0);

  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4 sm:p-6 shadow-sm">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
        <div>
          <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">Allocation</h2>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
            {owner} net worth by asset class
          </p>
        </div>
        <div className="flex items-center gap-0.5 bg-gray-100 dark:bg-gray-800 rounded-md p-0.5 self-start">
          {OWNERS.map((o) => (
            <button
              key={o}
              onClick={() => setOwner(o)}
              className={`px-2.5 py-1 text-xs font-medium rounded transition-colors ${
                owner === o
                  ? "bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-50 shadow-sm"
                  : "text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-50"
              }`}
            >
              {o}
            </button>
          ))}
        </div>
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
