"use client";

import { useState } from "react";
import {
  CartesianGrid, Line, LineChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { type MonthlySpend, type DailySpend } from "@/lib/queries";
import NavBtn from "./nav-btn";

type Props = {
  monthly: MonthlySpend[];
  daily: DailySpend[];
};

const gbp = new Intl.NumberFormat("en-GB", {
  style: "currency",
  currency: "GBP",
  maximumFractionDigits: 0,
});

const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function monLabel(iso: string) {
  const [year, mon] = iso.split("-");
  return new Date(Number(year), Number(mon) - 1, 1).toLocaleDateString("en-GB", { month: "short", year: "2-digit" });
}

export default function SpendingChart({ monthly, daily }: Props) {
  const [trendView, setTrendView]       = useState<"year" | "month">("year");
  const [yearViewIdx, setYearViewIdx]   = useState(-1); // -1 = most recent year
  const [monthViewIdx, setMonthViewIdx] = useState(-1); // -1 = most recent month

  const now     = new Date();
  const nowYear = now.getUTCFullYear();
  const nowMon  = now.getUTCMonth() + 1;
  const nowDay  = now.getUTCDate();
  const nowMonKey = `${nowYear}-${String(nowMon).padStart(2, "0")}`;

  // ── Available years / months from data ────────────────────────────────────
  const availableYears  = [...new Set(monthly.map(m => m.month.slice(0, 4)))].sort();
  const availableMonths = monthly.map(m => m.month).sort();

  // ── Year view selection ───────────────────────────────────────────────────
  const actualYearIdx    = yearViewIdx === -1 ? availableYears.length - 1 : Math.min(yearViewIdx, availableYears.length - 1);
  const selYear          = availableYears[actualYearIdx] ?? String(nowYear);
  const compYear         = String(Number(selYear) - 1);

  // ── Month view selection ──────────────────────────────────────────────────
  const actualMonthIdx   = monthViewIdx === -1 ? availableMonths.length - 1 : Math.min(monthViewIdx, availableMonths.length - 1);
  const selMonKey        = availableMonths[actualMonthIdx] ?? nowMonKey;
  const [selMonYear, selMonNum] = selMonKey.split("-").map(Number);
  const selMonDays       = new Date(selMonYear, selMonNum, 0).getDate();
  const selDay           = selMonKey === nowMonKey ? nowDay : selMonDays;

  const prevMonYear  = selMonNum === 1 ? selMonYear - 1 : selMonYear;
  const prevMonNum   = selMonNum === 1 ? 12 : selMonNum - 1;
  const prevMonKey   = `${prevMonYear}-${String(prevMonNum).padStart(2, "0")}`;
  const prevMonDays  = new Date(prevMonYear, prevMonNum, 0).getDate();

  const selMonLabel  = monLabel(selMonKey);
  const prevMonLabel = monLabel(prevMonKey);

  // ── Year view: selected year vs previous year monthly totals ─────────────
  const monthMap: Record<string, number> = {};
  for (const m of monthly) monthMap[m.month] = m.total;

  const yearViewData = MONTH_NAMES.map((name, idx) => {
    const mm = String(idx + 1).padStart(2, "0");
    return {
      month: name,
      current: monthMap[`${selYear}-${mm}`] ?? null,
      prev:    monthMap[`${compYear}-${mm}`] ?? null,
    };
  }).filter(d => d.current != null || d.prev != null);

  // ── Month view: cumulative daily spend for selected month vs previous ─────
  const curDayMap: Record<number, number>  = {};
  const prevDayMap: Record<number, number> = {};
  for (const d of daily) {
    if (d.date.startsWith(selMonKey)) {
      const day = parseInt(d.date.slice(8, 10), 10);
      curDayMap[day]  = (curDayMap[day]  ?? 0) + d.total;
    } else if (d.date.startsWith(prevMonKey)) {
      const day = parseInt(d.date.slice(8, 10), 10);
      prevDayMap[day] = (prevDayMap[day] ?? 0) + d.total;
    }
  }

  let curCumul = 0, prevCumul = 0;
  const maxDayRange = Math.max(selDay, prevMonDays);
  const monthViewData = Array.from({ length: maxDayRange }, (_, i) => {
    const day = i + 1;
    if (day <= selDay)    curCumul  += curDayMap[day]  ?? 0;
    if (day <= prevMonDays) prevCumul += prevDayMap[day] ?? 0;
    return {
      day: String(day),
      current: day <= selDay      ? curCumul  : null,
      prev:    day <= prevMonDays ? prevCumul : null,
    };
  });

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const fmtGbp = (v: any, name: any): [string, string] => [gbp.format(Number(v ?? 0)), String(name)];

  const navLabelClass = "text-xs font-medium text-gray-500 tabular-nums";

  return (
    <div className="flex flex-col gap-4">

      {/* ── Spending Trend ─────────────────────────────────────────────────── */}
      <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4 sm:p-6 shadow-sm">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">Spending Trend</h2>
          <div className="flex items-center gap-0.5 bg-gray-100 dark:bg-gray-800 rounded-md p-0.5">
            {(["year", "month"] as const).map(v => (
              <button
                key={v}
                onClick={() => setTrendView(v)}
                className={`px-2.5 py-1 text-xs font-medium rounded transition-colors ${
                  trendView === v
                    ? "bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-50 shadow-sm"
                    : "text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-50"
                }`}
              >
                {v === "year" ? "Year" : "Month"}
              </button>
            ))}
          </div>
        </div>

        {/* Legend */}
        <div className="flex items-center gap-4 text-xs text-gray-500 mb-3">
          <span className="flex items-center gap-1.5">
            <svg width="20" height="4" className="shrink-0">
              <line x1="0" y1="2" x2="20" y2="2" stroke="#3b82f6" strokeWidth="2" />
            </svg>
            {trendView === "year" ? selYear : selMonLabel}
          </span>
          <span className="flex items-center gap-1.5">
            <svg width="20" height="4" className="shrink-0">
              <line x1="0" y1="2" x2="20" y2="2" stroke="#94a3b8" strokeWidth="2" strokeDasharray="4 3" />
            </svg>
            {trendView === "year" ? compYear : prevMonLabel}
          </span>
          {trendView === "month" && (
            <span className="text-gray-400 text-xs">cumulative</span>
          )}
        </div>

        <ResponsiveContainer width="100%" height={200}>
          {trendView === "year" ? (
            <LineChart data={yearViewData} margin={{ top: 4, right: 4, left: 0, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-gray-100 dark:stroke-gray-800" vertical={false} />
              <XAxis dataKey="month" tick={{ fontSize: 11, fill: "currentColor" }} tickLine={false} axisLine={false} />
              <YAxis tick={{ fontSize: 11, fill: "currentColor" }} tickLine={false} axisLine={false} tickFormatter={v => `£${(v / 1000).toFixed(1)}k`} width={42} />
              <Tooltip
                formatter={(v, name) => fmtGbp(v, name === "current" ? selYear : compYear)}
                contentStyle={{ fontSize: 12, borderRadius: 10, border: "1px solid rgba(0,0,0,0.08)" }}
              />
              <Line dataKey="prev"    stroke="#94a3b8" strokeWidth={2}   strokeDasharray="5 4" dot={false} connectNulls />
              <Line dataKey="current" stroke="#3b82f6" strokeWidth={2.5} dot={false} connectNulls />
            </LineChart>
          ) : (
            <LineChart data={monthViewData} margin={{ top: 4, right: 4, left: 0, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-gray-100 dark:stroke-gray-800" vertical={false} />
              <XAxis dataKey="day" tick={{ fontSize: 11, fill: "currentColor" }} tickLine={false} axisLine={false} interval={4} />
              <YAxis tick={{ fontSize: 11, fill: "currentColor" }} tickLine={false} axisLine={false} tickFormatter={v => `£${(v / 1000).toFixed(1)}k`} width={42} />
              <Tooltip
                formatter={(v, name) => fmtGbp(v, name === "current" ? selMonLabel : prevMonLabel)}
                labelFormatter={l => `Day ${l}`}
                contentStyle={{ fontSize: 12, borderRadius: 10, border: "1px solid rgba(0,0,0,0.08)" }}
              />
              <Line dataKey="prev"    stroke="#94a3b8" strokeWidth={2}   strokeDasharray="5 4" dot={false} connectNulls />
              <Line dataKey="current" stroke="#3b82f6" strokeWidth={2.5} dot={false} connectNulls />
            </LineChart>
          )}
        </ResponsiveContainer>

        {/* Year navigation */}
        {trendView === "year" && availableYears.length > 1 && (
          <div className="flex items-center justify-between mt-3">
            <NavBtn direction="left" onClick={() => setYearViewIdx(Math.max(0, actualYearIdx - 1))} disabled={actualYearIdx === 0} />
            <span className={navLabelClass}>{selYear} vs {compYear}</span>
            <NavBtn direction="right" onClick={() => setYearViewIdx(Math.min(availableYears.length - 1, actualYearIdx + 1))} disabled={actualYearIdx === availableYears.length - 1} />
          </div>
        )}

        {/* Month navigation */}
        {trendView === "month" && availableMonths.length > 1 && (
          <div className="flex items-center justify-between mt-3">
            <NavBtn direction="left" onClick={() => setMonthViewIdx(Math.max(0, actualMonthIdx - 1))} disabled={actualMonthIdx === 0} />
            <span className={navLabelClass}>{selMonLabel} vs {prevMonLabel}</span>
            <NavBtn direction="right" onClick={() => setMonthViewIdx(Math.min(availableMonths.length - 1, actualMonthIdx + 1))} disabled={actualMonthIdx === availableMonths.length - 1} />
          </div>
        )}
      </div>
    </div>
  );
}
