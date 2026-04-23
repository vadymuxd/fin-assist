"use client";

import { useMemo, useState } from "react";
import { AreaChart } from "@tremor/react";
import type { PortfolioSnapshot } from "@/lib/queries";

type Granularity = "D" | "W" | "M";

const benchmarkKeys = {
  "S&P 500": "spx",
  FTSE: "ftse",
  NDX: "ndx",
  MSCI: "msci",
  Gold: "gold",
} as const satisfies Record<string, keyof PortfolioSnapshot>;

type BenchmarkLabel = keyof typeof benchmarkKeys;

const benchmarkLabels = Object.keys(benchmarkKeys) as BenchmarkLabel[];

function aggregate(snapshots: PortfolioSnapshot[], granularity: Granularity): PortfolioSnapshot[] {
  if (granularity === "D" || snapshots.length <= 1) return snapshots;
  const bucket: Record<string, PortfolioSnapshot> = {};
  for (const s of snapshots) {
    const d = new Date(`${s.date}T00:00:00Z`);
    let key: string;
    if (granularity === "W") {
      const day = d.getUTCDay(); // 0=Sun ... 6=Sat
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

function toIndexed(
  snapshots: PortfolioSnapshot[],
  activeBenchmarks: BenchmarkLabel[]
): Array<Record<string, number | string>> {
  if (snapshots.length === 0) return [];
  const base = snapshots[0];
  return snapshots.map((s) => {
    const row: Record<string, number | string> = { date: s.date };
    row.Portfolio = (s.grand_total / base.grand_total) * 100;
    for (const label of activeBenchmarks) {
      const key = benchmarkKeys[label];
      const baseVal = base[key] as number;
      const val = s[key] as number;
      row[label] = baseVal > 0 ? (val / baseVal) * 100 : 100;
    }
    return row;
  });
}

export default function PortfolioChart({ snapshots }: { snapshots: PortfolioSnapshot[] }) {
  const [granularity, setGranularity] = useState<Granularity>("D");
  const [active, setActive] = useState<BenchmarkLabel[]>(["S&P 500"]);

  const data = useMemo(
    () => toIndexed(aggregate(snapshots, granularity), active),
    [snapshots, granularity, active]
  );

  const categories = ["Portfolio", ...active];
  const colors = ["blue", "slate", "emerald", "amber", "violet", "rose"];

  const toggleBenchmark = (label: BenchmarkLabel) => {
    setActive((prev) => (prev.includes(label) ? prev.filter((b) => b !== label) : [...prev, label]));
  };

  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4 sm:p-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
        <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-50">
          Portfolio Value <span className="text-gray-400 font-normal">(indexed to 100 at start)</span>
        </h2>
        <div className="flex items-center gap-1 bg-gray-100 dark:bg-gray-800 rounded-md p-0.5 self-start">
          {(["D", "W", "M"] as Granularity[]).map((g) => (
            <button
              key={g}
              onClick={() => setGranularity(g)}
              className={`px-3 py-1 text-xs font-medium rounded transition-colors ${
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

      <div className="flex flex-wrap gap-1.5 mb-4">
        {benchmarkLabels.map((label) => {
          const on = active.includes(label);
          return (
            <button
              key={label}
              onClick={() => toggleBenchmark(label)}
              className={`px-2.5 py-1 text-xs font-medium rounded-full border transition-colors ${
                on
                  ? "bg-gray-900 dark:bg-gray-50 text-white dark:text-gray-900 border-gray-900 dark:border-gray-50"
                  : "bg-transparent text-gray-600 dark:text-gray-400 border-gray-200 dark:border-gray-700 hover:border-gray-400 dark:hover:border-gray-500"
              }`}
            >
              {label}
            </button>
          );
        })}
      </div>

      {data.length < 2 ? (
        <div className="h-64 flex items-center justify-center text-sm text-gray-500 dark:text-gray-400">
          Not enough data yet — chart builds up as daily snapshots accumulate.
        </div>
      ) : (
        <AreaChart
          className="h-64 sm:h-80"
          data={data}
          index="date"
          categories={categories}
          colors={colors.slice(0, categories.length)}
          valueFormatter={(v: number) => `${v.toFixed(1)}`}
          showLegend={false}
          showYAxis
          showXAxis
          showGridLines
          startEndOnly
          yAxisWidth={44}
        />
      )}
    </div>
  );
}
