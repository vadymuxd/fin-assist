"use client";

import { useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { PensionSnapshot, PortfolioSnapshot } from "@/lib/queries";
import { buildComparisonData } from "@/lib/queries";

type SeriesKey = "customStocks" | "managed" | "spx" | "pensions" | "lisa";

const SERIES: { key: SeriesKey; label: string; color: string }[] = [
  { key: "customStocks", label: "Custom Stocks", color: "#2563eb" },
  { key: "managed",      label: "Managed Funds", color: "#10b981" },
  { key: "spx",          label: "S&P 500",       color: "#0ea5e9" },
  { key: "pensions",     label: "Pensions",       color: "#f59e0b" },
  { key: "lisa",         label: "Lisa",           color: "#d946ef" },
];

function shortDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", timeZone: "UTC" });
}

// Bucket daily points into ISO weeks (Monday-anchored), keeping the latest
// value in each week — so the X-axis steps by weeks rather than days.
function aggregateWeekly<T extends { date: string }>(rows: T[]): T[] {
  if (rows.length <= 1) return rows;
  const bucket: Record<string, T> = {};
  for (const r of rows) {
    const d = new Date(`${r.date}T00:00:00Z`);
    const day = d.getUTCDay();
    const diff = day === 0 ? -6 : 1 - day;
    const monday = new Date(d);
    monday.setUTCDate(d.getUTCDate() + diff);
    const key = monday.toISOString().slice(0, 10);
    bucket[key] = { ...r, date: key };
  }
  return Object.values(bucket).sort((a, b) => a.date.localeCompare(b.date));
}

type TooltipEntry = {
  dataKey?: string | number;
  value?: number | string | (number | string)[];
  color?: string;
  name?: string | number;
};

function CustomTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: readonly TooltipEntry[];
  label?: string | number;
}) {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white/95 dark:bg-gray-900/95 backdrop-blur p-3 shadow-lg text-xs">
      <div className="font-medium text-gray-900 dark:text-gray-50 mb-1.5">
        {typeof label === "string" ? shortDate(label) : ""}
      </div>
      <ul className="space-y-1">
        {payload.map((p, i) => {
          const v = typeof p.value === "number" ? p.value : Number(Array.isArray(p.value) ? p.value[0] : (p.value ?? 0));
          const diff = v - 100;
          return (
            <li key={String(p.dataKey ?? i)} className="flex items-center justify-between gap-4">
              <span className="flex items-center gap-1.5 text-gray-600 dark:text-gray-300">
                <span className="w-2 h-2 rounded-full" style={{ backgroundColor: p.color }} />
                {p.name}
              </span>
              <span className={`font-medium tabular-nums ${diff >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-red-500 dark:text-red-400"}`}>
                {diff >= 0 ? "+" : ""}{diff.toFixed(1)}%
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export default function ComparisonChart({
  portfolioSnapshots,
  pensionSnapshots,
}: {
  portfolioSnapshots: PortfolioSnapshot[];
  pensionSnapshots: PensionSnapshot[];
}) {
  const [active, setActive] = useState<SeriesKey[]>(["customStocks", "spx", "managed"]);

  const data = useMemo(
    () => aggregateWeekly(buildComparisonData(portfolioSnapshots, pensionSnapshots)),
    [portfolioSnapshots, pensionSnapshots],
  );

  const toggle = (key: SeriesKey) =>
    setActive((prev) => (prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]));

  const yFmt = (v: number) => `${(v - 100).toFixed(0)}%`;

  if (data.length < 2) {
    return (
      <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4 sm:p-6 shadow-sm">
        <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50 mb-1">Performance Comparison</h2>
        <div className="h-64 flex items-center justify-center text-sm text-gray-500 dark:text-gray-400">
          Not enough data yet.
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4 sm:p-6 shadow-sm">
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 mb-4">
        <div>
          <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">Performance Comparison</h2>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
            Indexed to 0% at {shortDate(data[0].date)} — relative growth since tracking start
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {SERIES.map(({ key, label, color }) => {
            const on = active.includes(key);
            return (
              <button
                key={key}
                onClick={() => toggle(key)}
                className={`flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full border transition-colors ${
                  on
                    ? "bg-gray-900 dark:bg-gray-50 text-white dark:text-gray-900 border-gray-900 dark:border-gray-50"
                    : "bg-transparent text-gray-600 dark:text-gray-400 border-gray-200 dark:border-gray-700 hover:border-gray-400 dark:hover:border-gray-500"
                }`}
              >
                <span className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
                {label}
              </button>
            );
          })}
        </div>
      </div>

      <div className="h-64 sm:h-80 -ml-2">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
            <CartesianGrid
              strokeDasharray="3 3"
              className="stroke-gray-200 dark:stroke-gray-800"
              vertical={false}
            />
            <XAxis
              dataKey="date"
              tickFormatter={shortDate}
              tick={{ fontSize: 11, fill: "currentColor" }}
              className="text-gray-400 dark:text-gray-500"
              tickLine={false}
              axisLine={false}
              minTickGap={32}
            />
            <YAxis
              tick={{ fontSize: 11, fill: "currentColor" }}
              className="text-gray-400 dark:text-gray-500"
              tickLine={false}
              axisLine={false}
              tickFormatter={yFmt}
              width={52}
              domain={["auto", "auto"]}
            />
            <Tooltip
              content={(props) => (
                <CustomTooltip
                  active={props.active}
                  payload={props.payload as readonly TooltipEntry[] | undefined}
                  label={props.label}
                />
              )}
              cursor={{ stroke: "#94a3b8", strokeDasharray: "3 3" }}
            />
            {SERIES.filter(({ key }) => active.includes(key)).map(({ key, label, color }) => (
              <Line
                key={key}
                type="monotone"
                dataKey={key}
                name={label}
                stroke={color}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4 }}
                connectNulls
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
