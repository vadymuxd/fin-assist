"use client";

import { useMemo, useState } from "react";
import {
  Area,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  ComposedChart,
} from "recharts";
import type { PortfolioSnapshot } from "@/lib/queries";

type Granularity = "D" | "W" | "M";
type Mode = "value" | "performance";

const benchmarkKeys = {
  "S&P 500": "spx",
  FTSE: "ftse",
  NDX: "ndx",
  MSCI: "msci",
  Gold: "gold",
  Lisa: "lisa_total",
} as const satisfies Record<string, keyof PortfolioSnapshot>;

type BenchmarkLabel = keyof typeof benchmarkKeys;
const benchmarkLabels = Object.keys(benchmarkKeys) as BenchmarkLabel[];

const seriesColor: Record<string, string> = {
  Portfolio: "#2563eb",
  "S&P 500": "#0ea5e9",
  FTSE: "#10b981",
  NDX: "#f59e0b",
  MSCI: "#8b5cf6",
  Gold: "#f43f5e",
  Lisa: "#d946ef",
};

const gbp = new Intl.NumberFormat("en-GB", {
  style: "currency",
  currency: "GBP",
  maximumFractionDigits: 0,
});

function aggregate(snapshots: PortfolioSnapshot[], g: Granularity): PortfolioSnapshot[] {
  if (g === "D" || snapshots.length <= 1) return snapshots;
  const bucket: Record<string, PortfolioSnapshot> = {};
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

type Row = { date: string; Portfolio: number } & Partial<Record<BenchmarkLabel, number | null>>;

function buildValueData(snapshots: PortfolioSnapshot[]): Row[] {
  return snapshots.map((s) => ({ date: s.date, Portfolio: s.vadym_total }));
}

function buildPerformanceData(
  snapshots: PortfolioSnapshot[],
  active: BenchmarkLabel[]
): { rows: Row[]; activeWithData: BenchmarkLabel[] } {
  if (snapshots.length === 0) return { rows: [], activeWithData: [] };

  // Portfolio line = stocks-only organic performance, indexed to 100.
  // ratio = self_managed / stocks_started_value (col G / col I in the sheet).
  // Cash and new BUYs both cancel out of this ratio, so it reflects only
  // organic price movement on the stocks the user owns.
  const stockValues: number[] = snapshots.map((s) => {
    const started = s.stocks_started_value ?? 0;
    return started > 0 ? (s.self_managed / started) * 100 : 100;
  });

  // Anchor each benchmark to its first non-null point, so a series with a
  // late start (e.g. gold backfilled later) still indexes to 100 from its
  // own first sample rather than being dropped.
  const baseBench: Partial<Record<BenchmarkLabel, number | null>> = {};
  for (const label of active) {
    const k = benchmarkKeys[label];
    const firstValid = snapshots.find((s) => {
      const v = s[k];
      return typeof v === "number" && v > 0;
    });
    baseBench[label] = firstValid ? (firstValid[k] as number) : null;
  }
  const activeWithData = active.filter((l) => baseBench[l] != null);
  const rows: Row[] = snapshots.map((s, i) => {
    const r: Row = { date: s.date, Portfolio: stockValues[i] };
    for (const label of activeWithData) {
      const k = benchmarkKeys[label];
      const v = s[k];
      const b = baseBench[label]!;
      r[label] = typeof v === "number" && v > 0 ? (v / b) * 100 : null;
    }
    return r;
  });
  return { rows, activeWithData };
}

function shortDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", timeZone: "UTC" });
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
  mode,
}: {
  active?: boolean;
  payload?: readonly TooltipEntry[];
  label?: string | number;
  mode: Mode;
}) {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white/95 dark:bg-gray-900/95 backdrop-blur p-3 shadow-lg text-xs">
      <div className="font-medium text-gray-900 dark:text-gray-50 mb-1.5">
        {typeof label === "string" ? shortDate(label) : ""}
      </div>
      <ul className="space-y-1">
        {payload.map((p, i) => {
          const v = typeof p.value === "number" ? p.value : Number(Array.isArray(p.value) ? p.value[0] : p.value ?? 0);
          return (
            <li key={String(p.dataKey ?? i)} className="flex items-center justify-between gap-4">
              <span className="flex items-center gap-1.5 text-gray-600 dark:text-gray-300">
                <span className="w-2 h-2 rounded-full" style={{ backgroundColor: p.color }} />
                {p.name}
              </span>
              <span className="font-medium tabular-nums text-gray-900 dark:text-gray-50">
                {mode === "value" ? gbp.format(v) : v.toFixed(1)}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export default function PortfolioChart({ snapshots }: { snapshots: PortfolioSnapshot[] }) {
  const [granularity, setGranularity] = useState<Granularity>("D");
  const [mode, setMode] = useState<Mode>("value");
  const [active, setActive] = useState<BenchmarkLabel[]>(["S&P 500"]);

  const aggregated = useMemo(() => aggregate(snapshots, granularity), [snapshots, granularity]);

  const { rows, activeWithData } = useMemo(() => {
    if (mode === "value") {
      return { rows: buildValueData(aggregated), activeWithData: [] as BenchmarkLabel[] };
    }
    return buildPerformanceData(aggregated, active);
  }, [aggregated, mode, active]);

  const series: string[] = mode === "value" ? ["Portfolio"] : ["Portfolio", ...activeWithData];

  const toggleBenchmark = (label: BenchmarkLabel) => {
    setActive((prev) => (prev.includes(label) ? prev.filter((b) => b !== label) : [...prev, label]));
  };

  const yFmt = (v: number) => (mode === "value" ? gbp.format(v) : v.toFixed(0));

  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4 sm:p-6 shadow-sm">
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 mb-4">
        <div>
          <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">
            {mode === "value" ? "Portfolio Value" : "Portfolio Performance"}
          </h2>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
            {mode === "value"
              ? "Grand total over time, in GBP"
              : "All series indexed to 100 at start — compares relative growth"}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-0.5 bg-gray-100 dark:bg-gray-800 rounded-md p-0.5">
            {(["value", "performance"] as Mode[]).map((m) => (
              <button
                key={m}
                onClick={() => {
                  setMode(m);
                  if (m === "performance" && granularity === "D") setGranularity("W");
                }}
                className={`px-2.5 py-1 text-xs font-medium rounded transition-colors ${
                  mode === m
                    ? "bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-50 shadow-sm"
                    : "text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-50"
                }`}
              >
                {m === "value" ? "£" : "%"}
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

      {mode === "performance" && (
        <div className="flex flex-wrap gap-1.5 mb-4">
          {benchmarkLabels.map((label) => {
            const on = active.includes(label);
            return (
              <button
                key={label}
                onClick={() => toggleBenchmark(label)}
                className={`flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full border transition-colors ${
                  on
                    ? "bg-gray-900 dark:bg-gray-50 text-white dark:text-gray-900 border-gray-900 dark:border-gray-50"
                    : "bg-transparent text-gray-600 dark:text-gray-400 border-gray-200 dark:border-gray-700 hover:border-gray-400 dark:hover:border-gray-500"
                }`}
              >
                <span
                  className="w-2 h-2 rounded-full"
                  style={{ backgroundColor: seriesColor[label] }}
                />
                {label}
              </button>
            );
          })}
        </div>
      )}

      {rows.length < 2 ? (
        <div className="h-64 flex items-center justify-center text-sm text-gray-500 dark:text-gray-400 text-center px-4">
          Not enough data yet — chart builds up as daily snapshots accumulate.
        </div>
      ) : (
        <div className="h-64 sm:h-80 -ml-2">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={rows} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="portfolioFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#2563eb" stopOpacity={0.25} />
                  <stop offset="100%" stopColor="#2563eb" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--grid, 229 231 235))" className="stroke-gray-200 dark:stroke-gray-800" vertical={false} />
              <XAxis
                dataKey="date"
                tickFormatter={shortDate}
                tick={{ fontSize: 11, fill: "currentColor" }}
                stroke="currentColor"
                className="text-gray-400 dark:text-gray-500"
                tickLine={false}
                axisLine={false}
                minTickGap={32}
              />
              <YAxis
                tick={{ fontSize: 11, fill: "currentColor" }}
                stroke="currentColor"
                className="text-gray-400 dark:text-gray-500"
                tickLine={false}
                axisLine={false}
                tickFormatter={yFmt}
                width={64}
                domain={mode === "performance" ? ["auto", "auto"] : ["dataMin - 200", "dataMax + 200"]}
              />
              <Tooltip
                content={(props) => (
                  <CustomTooltip
                    active={props.active}
                    payload={props.payload as readonly TooltipEntry[] | undefined}
                    label={props.label}
                    mode={mode}
                  />
                )}
                cursor={{ stroke: "#94a3b8", strokeDasharray: "3 3" }}
              />
              <Legend
                verticalAlign="bottom"
                height={28}
                iconType="circle"
                wrapperStyle={{ fontSize: 11, paddingTop: 4 }}
              />
              <Area
                type="monotone"
                dataKey="Portfolio"
                stroke="#2563eb"
                strokeWidth={2.25}
                fill="url(#portfolioFill)"
                dot={false}
                activeDot={{ r: 4 }}
                isAnimationActive={false}
              />
              {series.slice(1).map((s) => (
                <Line
                  key={s}
                  type="monotone"
                  dataKey={s}
                  stroke={seriesColor[s] ?? "#64748b"}
                  strokeWidth={1.5}
                  dot={false}
                  activeDot={{ r: 3 }}
                  connectNulls
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
