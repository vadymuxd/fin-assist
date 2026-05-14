"use client";

import { useMemo, useState } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { type SavingsSnapshot } from "@/lib/queries";

type Granularity = "D" | "W" | "M";
type Filter = "Total" | "Vadym" | "Lisa" | "Joint" | "Trend";

const gbp = new Intl.NumberFormat("en-GB", {
  style: "currency",
  currency: "GBP",
  maximumFractionDigits: 0,
});

function aggregate(snapshots: SavingsSnapshot[], g: Granularity): SavingsSnapshot[] {
  if (g === "D" || snapshots.length <= 1) return snapshots;
  const bucket: Record<string, SavingsSnapshot> = {};
  for (const s of snapshots) {
    const d = new Date(`${s.date}T00:00:00Z`);
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
    bucket[key] = { ...s, date: key };
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

type SingleRow = { date: string; value: number };
type TrendRow  = { date: string; vadym: number; lisa: number | null };

type TooltipPayloadItem = { name?: string; value?: number | string | (number | string)[]; color?: string };

function SingleTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: readonly TooltipPayloadItem[];
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white/95 dark:bg-gray-900/95 backdrop-blur p-3 shadow-lg text-xs">
      <div className="font-medium text-gray-900 dark:text-gray-50 mb-1.5">
        {typeof label === "string" ? shortDate(label) : ""}
      </div>
      <div className="flex items-center gap-2">
        <span className="w-2 h-2 rounded-full bg-emerald-500" />
        <span className="font-medium tabular-nums text-gray-900 dark:text-gray-50">
          {gbp.format(Number(Array.isArray(payload[0]?.value) ? (payload[0]?.value[0] ?? 0) : (payload[0]?.value ?? 0)))}
        </span>
      </div>
    </div>
  );
}

function TrendTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: readonly TooltipPayloadItem[];
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white/95 dark:bg-gray-900/95 backdrop-blur p-3 shadow-lg text-xs">
      <div className="font-medium text-gray-900 dark:text-gray-50 mb-1.5">
        {typeof label === "string" ? shortDate(label) : ""}
      </div>
      {payload.map((p) => (
        p.value != null && (
          <div key={p.name} className="flex items-center gap-2 mt-0.5">
            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: p.color }} />
            <span className="text-gray-500 dark:text-gray-400 w-10">{p.name}</span>
            <span className="font-medium tabular-nums text-gray-900 dark:text-gray-50">
              {gbp.format(Number(p.value))}
            </span>
          </div>
        )
      ))}
    </div>
  );
}

export default function SavingsChart({ snapshots }: { snapshots: SavingsSnapshot[] }) {
  const [granularity, setGranularity] = useState<Granularity>("D");
  const [filter, setFilter] = useState<Filter>("Total");

  const aggregated = useMemo(() => aggregate(snapshots, granularity), [snapshots, granularity]);

  const singleRows = useMemo((): SingleRow[] =>
    aggregated.map((s) => ({
      date: s.date,
      value:
        filter === "Vadym" ? s.vadym_total
        : filter === "Lisa"  ? (s.lisa_total ?? 0)
        : filter === "Joint" ? s.joint_total
        : s.vadym_total + (s.lisa_total ?? 0) + s.joint_total,
    })),
  [aggregated, filter]);

  const trendRows = useMemo((): TrendRow[] =>
    aggregated.map((s) => ({
      date: s.date,
      vadym: s.vadym_total,
      lisa: s.lisa_total,
    })),
  [aggregated]);

  const isTrend = filter === "Trend";

  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4 sm:p-6 shadow-sm">
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 mb-4">
        <div>
          <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">Savings Growth</h2>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
            {isTrend ? "Vadym vs Lisa savings over time" : "Total balance over time, in GBP"}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-0.5 bg-gray-100 dark:bg-gray-800 rounded-md p-0.5">
            {(["Total", "Vadym", "Lisa", "Joint", "Trend"] as Filter[]).map((f) => (
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

      {(isTrend ? trendRows.length < 2 : singleRows.length < 2) ? (
        <div className="h-64 flex items-center justify-center text-sm text-gray-500 dark:text-gray-400 text-center px-4">
          Not enough data yet — chart builds up as monthly snapshots accumulate.
        </div>
      ) : isTrend ? (
        <div className="h-64 sm:h-80 -ml-2">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={trendRows} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="vadymFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#6366f1" stopOpacity={0.2} />
                  <stop offset="100%" stopColor="#6366f1" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="lisaFill" x1="0" y1="0" x2="0" y2="1">
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
                width={64}
              />
              <Tooltip content={(props) => <TrendTooltip active={props.active} payload={props.payload as readonly TooltipPayloadItem[] | undefined} label={props.label as string | undefined} />} cursor={{ stroke: "#94a3b8", strokeDasharray: "3 3" }} />
              <Legend
                iconType="circle"
                iconSize={8}
                wrapperStyle={{ fontSize: 11, paddingTop: 8 }}
              />
              <Area
                type="monotone"
                dataKey="vadym"
                name="Vadym"
                stroke="#6366f1"
                strokeWidth={2.25}
                fill="url(#vadymFill)"
                dot={false}
                activeDot={{ r: 4 }}
                isAnimationActive={false}
                connectNulls
              />
              <Area
                type="monotone"
                dataKey="lisa"
                name="Lisa"
                stroke="#ec4899"
                strokeWidth={2.25}
                fill="url(#lisaFill)"
                dot={false}
                activeDot={{ r: 4 }}
                isAnimationActive={false}
                connectNulls
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="h-64 sm:h-80 -ml-2">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={singleRows} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="savingsFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#10b981" stopOpacity={0.25} />
                  <stop offset="100%" stopColor="#10b981" stopOpacity={0} />
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
                width={64}
                domain={["dataMin - 200", "dataMax + 200"]}
              />
              <Tooltip content={(props) => <SingleTooltip active={props.active} payload={props.payload as readonly TooltipPayloadItem[] | undefined} label={props.label as string | undefined} />} cursor={{ stroke: "#94a3b8", strokeDasharray: "3 3" }} />
              <Area
                type="monotone"
                dataKey="value"
                name="Savings"
                stroke="#10b981"
                strokeWidth={2.25}
                fill="url(#savingsFill)"
                dot={false}
                activeDot={{ r: 4 }}
                isAnimationActive={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
