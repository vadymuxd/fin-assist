"use client";

import { useMemo, useState } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { NetWorthPoint } from "@/lib/queries";

type Granularity = "D" | "W" | "M";
type Filter = "Joint" | "Vadym" | "Lisa" | "Trend" | "Breakdown";

const gbp = new Intl.NumberFormat("en-GB", {
  style: "currency",
  currency: "GBP",
  maximumFractionDigits: 0,
});

const breakdownSeries = [
  { key: "investments" as const,     name: "Investments",     color: "#2563eb" },
  { key: "savings" as const,         name: "Savings",         color: "#10b981" },
  { key: "pensions" as const,        name: "Pensions",        color: "#f59e0b" },
  { key: "mortgage_equity" as const, name: "Mortgage Equity", color: "#f97316" },
];

function aggregate(data: NetWorthPoint[], g: Granularity): NetWorthPoint[] {
  if (g === "D" || data.length <= 1) return data;
  const bucket: Record<string, NetWorthPoint> = {};
  for (const p of data) {
    const d = new Date(`${p.date}T00:00:00Z`);
    let key: string;
    if (g === "W") {
      const day = d.getUTCDay();
      const diff = day === 0 ? -6 : 1 - day;
      const monday = new Date(d);
      monday.setUTCDate(d.getUTCDate() + diff);
      key = monday.toISOString().slice(0, 10);
    } else {
      key = `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}-01`;
    }
    bucket[key] = { ...p, date: key };
  }
  return Object.values(bucket).sort((a, b) => a.date.localeCompare(b.date));
}

function shortDate(iso: string) {
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    timeZone: "UTC",
  });
}

type TooltipEntry = { dataKey?: string | number; value?: number; color?: string; name?: string | number };

function CustomTooltip({ active, payload, label }: { active?: boolean; payload?: readonly TooltipEntry[]; label?: string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white/95 dark:bg-gray-900/95 backdrop-blur p-3 shadow-lg text-xs">
      <div className="font-medium text-gray-900 dark:text-gray-50 mb-1.5">
        {typeof label === "string" ? shortDate(label) : ""}
      </div>
      <ul className="space-y-1">
        {payload.map((p, i) => (
          <li key={String(p.dataKey ?? i)} className="flex items-center justify-between gap-4">
            <span className="flex items-center gap-1.5 text-gray-600 dark:text-gray-300">
              <span className="w-2 h-2 rounded-full" style={{ backgroundColor: p.color }} />
              {p.name}
            </span>
            <span className="font-medium tabular-nums text-gray-900 dark:text-gray-50">
              {gbp.format(p.value ?? 0)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function NetWorthChart({ data }: { data: NetWorthPoint[] }) {
  const [granularity, setGranularity] = useState<Granularity>("D");
  const [filter, setFilter] = useState<Filter>("Joint");

  const rows = useMemo(() => aggregate(data, granularity), [data, granularity]);

  const isTrend     = filter === "Trend";
  const isBreakdown = filter === "Breakdown";

  const singleDataKey =
    filter === "Vadym" ? "vadym_net_worth"
    : filter === "Lisa" ? "lisa_net_worth"
    : "net_worth";

  const subtitle =
    isTrend     ? "Vadym vs Lisa net worth over time"
    : isBreakdown ? "Investments + Savings + Pensions + Mortgage Equity"
    : filter === "Vadym" ? "Vadym net worth over time"
    : filter === "Lisa"  ? "Lisa net worth over time"
    : "Combined net worth over time";

  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4 sm:p-6 shadow-sm">
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 mb-4">
        <div>
          <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">Net Worth Over Time</h2>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{subtitle}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-0.5 bg-gray-100 dark:bg-gray-800 rounded-md p-0.5">
            {(["Joint", "Vadym", "Lisa", "Trend", "Breakdown"] as Filter[]).map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`px-2.5 py-1 text-xs font-medium rounded transition-colors ${
                  filter === f
                    ? "bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-50 shadow-sm"
                    : "text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-50"
                }`}
              >
                {f}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-0.5 bg-gray-100 dark:bg-gray-800 rounded-md p-0.5">
            {(["D", "W", "M"] as Granularity[]).map((g) => (
              <button
                key={g}
                onClick={() => setGranularity(g)}
                className={`px-2.5 py-1 text-xs font-medium rounded transition-colors ${
                  granularity === g
                    ? "bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-50 shadow-sm"
                    : "text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-50"
                }`}
              >
                {g}
              </button>
            ))}
          </div>
        </div>
      </div>

      {rows.length < 2 ? (
        <div className="h-64 flex items-center justify-center text-sm text-gray-500 dark:text-gray-400 text-center px-4">
          Not enough data yet — the chart will build up as snapshots accumulate.
        </div>
      ) : (
        <div className="h-64 sm:h-80 -ml-2">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={rows} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="nwJointFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#8b5cf6" stopOpacity={0.22} />
                  <stop offset="100%" stopColor="#8b5cf6" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="nwVadymFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#6366f1" stopOpacity={0.2} />
                  <stop offset="100%" stopColor="#6366f1" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="nwLisaFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#ec4899" stopOpacity={0.2} />
                  <stop offset="100%" stopColor="#ec4899" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-800" vertical={false} />
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
                tickFormatter={(v) => gbp.format(v)}
                width={72}
                domain={["dataMin - 500", "dataMax + 500"]}
              />
              <Tooltip
                content={(props) => (
                  <CustomTooltip
                    active={props.active}
                    payload={props.payload as readonly TooltipEntry[] | undefined}
                    label={props.label as string | undefined}
                  />
                )}
                cursor={{ stroke: "#94a3b8", strokeDasharray: "3 3" }}
              />
              {(isTrend || isBreakdown) && (
                <Legend verticalAlign="bottom" height={28} iconType="circle" wrapperStyle={{ fontSize: 11, paddingTop: 4 }} />
              )}

              {/* Single-line views */}
              {!isTrend && !isBreakdown && (
                <Area
                  type="monotone"
                  dataKey={singleDataKey}
                  name={filter === "Vadym" ? "Vadym" : filter === "Lisa" ? "Lisa" : "Net Worth"}
                  stroke={filter === "Vadym" ? "#6366f1" : filter === "Lisa" ? "#ec4899" : "#8b5cf6"}
                  strokeWidth={2.25}
                  fill={filter === "Vadym" ? "url(#nwVadymFill)" : filter === "Lisa" ? "url(#nwLisaFill)" : "url(#nwJointFill)"}
                  dot={false}
                  activeDot={{ r: 4 }}
                  isAnimationActive={false}
                />
              )}

              {/* Trend: Vadym vs Lisa dual-line */}
              {isTrend && (
                <>
                  <Area
                    type="monotone"
                    dataKey="vadym_net_worth"
                    name="Vadym"
                    stroke="#6366f1"
                    strokeWidth={2.25}
                    fill="url(#nwVadymFill)"
                    dot={false}
                    activeDot={{ r: 4 }}
                    isAnimationActive={false}
                    connectNulls
                  />
                  <Area
                    type="monotone"
                    dataKey="lisa_net_worth"
                    name="Lisa"
                    stroke="#ec4899"
                    strokeWidth={2.25}
                    fill="url(#nwLisaFill)"
                    dot={false}
                    activeDot={{ r: 4 }}
                    isAnimationActive={false}
                    connectNulls
                  />
                </>
              )}

              {/* Breakdown: 4 component lines (joint) */}
              {isBreakdown && breakdownSeries.map((s) => (
                <Line
                  key={s.key}
                  type="monotone"
                  dataKey={s.key}
                  name={s.name}
                  stroke={s.color}
                  strokeWidth={1.5}
                  dot={false}
                  activeDot={{ r: 3 }}
                  isAnimationActive={false}
                />
              ))}
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
