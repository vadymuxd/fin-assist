"use client";

import { useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Line, LineChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { type MonthlySpend, type WeeklySpend } from "@/lib/queries";

type Props = {
  monthly: MonthlySpend[];
  weekly: WeeklySpend[];
};

const gbp = new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP", maximumFractionDigits: 0 });

const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function weekLabel(iso: string) {
  const d = new Date(iso + "T00:00:00Z");
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
}

export default function SpendingChart({ monthly, weekly }: Props) {
  const [barGranularity, setBarGranularity] = useState<"W" | "M">("M");

  // ── Year-over-year line chart ─────────────────────────────────────────────
  const yoyMap: Record<string, { "2025": number | null; "2026": number | null }> = {};
  for (const m of monthly) {
    const [year, mon] = m.month.split("-");
    const key = MONTH_NAMES[Number(mon) - 1];
    if (!yoyMap[key]) yoyMap[key] = { "2025": null, "2026": null };
    yoyMap[key][year as "2025" | "2026"] = m.total;
  }
  const yoyData = MONTH_NAMES.map((name) => ({
    month: name,
    "2025": yoyMap[name]?.["2025"] ?? null,
    "2026": yoyMap[name]?.["2026"] ?? null,
  })).filter(d => d["2025"] != null || d["2026"] != null);

  // ── Bar chart data ────────────────────────────────────────────────────────
  const barData =
    barGranularity === "M"
      ? monthly.map((m) => {
          const [year, mon] = m.month.split("-");
          return { period: `${MONTH_NAMES[Number(mon) - 1]} '${year.slice(2)}`, total: m.total };
        })
      : weekly.map((w) => ({ period: weekLabel(w.week), total: w.total }));

  return (
    <div className="flex flex-col gap-4">
      {/* Year-over-year line chart */}
      <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-950 p-4">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Monthly Spend</h2>
          <div className="flex items-center gap-3 text-xs text-gray-500">
            <span className="flex items-center gap-1.5">
              <svg width="20" height="4" className="shrink-0"><line x1="0" y1="2" x2="20" y2="2" stroke="#3b82f6" strokeWidth="2"/></svg>
              2026
            </span>
            <span className="flex items-center gap-1.5">
              <svg width="20" height="4" className="shrink-0"><line x1="0" y1="2" x2="20" y2="2" stroke="#94a3b8" strokeWidth="2" strokeDasharray="4 3"/></svg>
              2025
            </span>
          </div>
        </div>
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={yoyData} margin={{ top: 4, right: 4, left: 0, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-gray-100 dark:stroke-gray-800" vertical={false} />
            <XAxis dataKey="month" tick={{ fontSize: 10, fill: "currentColor" }} tickLine={false} axisLine={false} />
            <YAxis
              tick={{ fontSize: 10, fill: "currentColor" }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v) => `£${(v / 1000).toFixed(1)}k`}
              width={42}
            />
            <Tooltip
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              formatter={(v: any, name: any) => [gbp.format(Number(v ?? 0)), name]}
              contentStyle={{ fontSize: 12, borderRadius: 10, border: "1px solid rgba(0,0,0,0.08)" }}
            />
            <Line
              dataKey="2025"
              stroke="#94a3b8"
              strokeWidth={2}
              strokeDasharray="5 4"
              dot={false}
              connectNulls
            />
            <Line
              dataKey="2026"
              stroke="#3b82f6"
              strokeWidth={2.5}
              dot={false}
              connectNulls
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Bar chart with W/M toggle */}
      <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-950 p-4">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Spend by Period</h2>
          <div className="flex rounded-lg border border-gray-200 dark:border-gray-800 overflow-hidden text-xs">
            {(["W", "M"] as const).map((g) => (
              <button
                key={g}
                onClick={() => setBarGranularity(g)}
                className={`px-3 py-1 font-medium transition-colors ${
                  barGranularity === g
                    ? "bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900"
                    : "text-gray-500 hover:bg-gray-50 dark:hover:bg-gray-900"
                }`}
              >
                {g === "W" ? "Weekly" : "Monthly"}
              </button>
            ))}
          </div>
        </div>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart
            data={barData}
            margin={{ top: 4, right: 4, left: 0, bottom: 4 }}
            barCategoryGap={barGranularity === "W" ? "10%" : "20%"}
          >
            <CartesianGrid strokeDasharray="3 3" className="stroke-gray-100 dark:stroke-gray-800" vertical={false} />
            <XAxis
              dataKey="period"
              tick={{ fontSize: 9, fill: "currentColor" }}
              tickLine={false}
              axisLine={false}
              interval={barGranularity === "W" ? 3 : 0}
            />
            <YAxis
              tick={{ fontSize: 10, fill: "currentColor" }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v) => `£${(v / 1000).toFixed(1)}k`}
              width={42}
            />
            <Tooltip
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              formatter={(v: any) => [gbp.format(Number(v ?? 0)), "Spend"]}
              contentStyle={{ fontSize: 12, borderRadius: 10, border: "1px solid rgba(0,0,0,0.08)" }}
            />
            <Bar dataKey="total" fill="#3b82f6" radius={[3, 3, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
