"use client";

import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip,
} from "recharts";
import { type MonthlySpend, type DailySpend, type MerchantSpend, type DaySpend } from "@/lib/queries";

const gbp    = new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP", maximumFractionDigits: 0 });
const gbpDec = new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP", maximumFractionDigits: 2 });

function daysInMonth(year: number, month: number) {
  return new Date(year, month, 0).getDate();
}

// ── Hero: This month with budget chart ────────────────────────────────────────
export function ThisMonthHero({ monthly, daily, budget }: { monthly: MonthlySpend[]; daily: DailySpend[]; budget: number }) {
  const now          = new Date();
  const year         = now.getFullYear();
  const month        = now.getMonth() + 1;
  const dayOfMonth   = now.getDate();
  const totalDays    = daysInMonth(year, month);
  const daysLeft     = totalDays - dayOfMonth;
  const currentKey   = `${year}-${String(month).padStart(2, "0")}`;
  const prevKey      = month === 1
    ? `${year - 1}-12`
    : `${year}-${String(month - 1).padStart(2, "0")}`;

  const spent     = monthly.find(m => m.month === currentKey)?.total ?? 0;
  const lastTotal = monthly.find(m => m.month === prevKey)?.total ?? 0;
  const dailyRate = dayOfMonth > 0 ? spent / dayOfMonth : 0;
  const projected = Math.round(dailyRate * totalDays);
  const pctChange = lastTotal > 0 ? ((projected - lastTotal) / lastTotal) * 100 : null;
  const overBudget = spent > budget;

  // Cumulative daily spend for current month
  const dayMap: Record<number, number> = {};
  for (const d of daily) {
    if (d.date.startsWith(currentKey)) {
      const day = parseInt(d.date.slice(8, 10), 10);
      dayMap[day] = (dayMap[day] ?? 0) + d.total;
    }
  }

  // Both lines descend: budget → 0 (remaining budget left)
  let cumul = 0;
  const chartData = Array.from({ length: totalDays }, (_, i) => {
    const day    = i + 1;
    const isDone = day <= dayOfMonth;
    if (isDone) cumul += dayMap[day] ?? 0;
    return {
      day: String(day),
      actual: isDone ? Math.round(budget - cumul) : null,
      target: Math.round(budget - (budget / totalDays) * day),
    };
  });

  const minActual = Math.min(...chartData.map(d => d.actual ?? 0));
  const yMin = Math.min(0, Math.floor(minActual / 500) * 500);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const fmtTooltip = (v: any, name: any): [string, string] => [gbp.format(Number(v ?? 0)), name === "actual" ? "Remaining" : "Target pace"];

  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4 sm:p-6 shadow-sm">
      {/* Header row */}
      <div className="flex items-start justify-between gap-4 mb-4">
        <div>
          <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1">
            This Month
          </p>
          <div className={`text-3xl font-bold tabular-nums ${overBudget ? "text-red-500 dark:text-red-400" : "text-gray-900 dark:text-gray-50"}`}>
            {gbp.format(spent)}
          </div>
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
            Budget: <span className="font-medium text-gray-600 dark:text-gray-400">{gbp.format(budget)}</span>
            {"  ·  "}{daysLeft} days left{"  ·  "}{gbpDec.format(dailyRate)}/day
          </p>
        </div>
        <div className="text-xs text-right space-y-0.5 shrink-0">
          <div className="text-gray-500 dark:text-gray-400">
            Projected: <span className="font-medium tabular-nums text-gray-800 dark:text-gray-200">{gbp.format(projected)}</span>
          </div>
          {lastTotal > 0 && pctChange != null && (
            <div className="text-gray-500 dark:text-gray-400">
              vs last month:{" "}
              <span className={`font-medium tabular-nums ${pctChange > 0 ? "text-red-500 dark:text-red-400" : "text-emerald-600 dark:text-emerald-400"}`}>
                {pctChange > 0 ? "+" : ""}{pctChange.toFixed(0)}%
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Budget pace chart */}
      <ResponsiveContainer width="100%" height={130}>
        <LineChart data={chartData} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
          <XAxis
            dataKey="day"
            tick={{ fontSize: 11, fill: "currentColor" }}
            tickLine={false}
            axisLine={false}
            interval={4}
          />
          <YAxis
            tick={{ fontSize: 11, fill: "currentColor" }}
            tickLine={false}
            axisLine={false}
            tickFormatter={v => v === 0 ? "£0" : `£${(v / 1000).toFixed(0)}k`}
            width={42}
            domain={[yMin, budget]}
          />
          <Tooltip
            formatter={fmtTooltip}
            labelFormatter={l => `Day ${l}`}
            contentStyle={{ fontSize: 12, borderRadius: 10, border: "1px solid rgba(0,0,0,0.08)" }}
          />
          <Line dataKey="target" stroke="#ef4444" strokeWidth={1.5} strokeDasharray="5 4" dot={false} connectNulls />
          <Line dataKey="actual" stroke="#3b82f6" strokeWidth={2.5} dot={false} connectNulls />
        </LineChart>
      </ResponsiveContainer>

      {/* Legend */}
      <div className="flex items-center gap-4 text-xs text-gray-500 dark:text-gray-400 mt-2">
        <span className="flex items-center gap-1.5">
          <svg width="20" height="4" className="shrink-0">
            <line x1="0" y1="2" x2="20" y2="2" stroke="#3b82f6" strokeWidth="2" />
          </svg>
          Budget remaining
        </span>
        <span className="flex items-center gap-1.5">
          <svg width="20" height="4" className="shrink-0">
            <line x1="0" y1="2" x2="20" y2="2" stroke="#ef4444" strokeWidth="2" strokeDasharray="5 4" />
          </svg>
          Target pace
        </span>
      </div>
    </div>
  );
}

// ── Card: Top merchants ───────────────────────────────────────────────────────
function TopMerchantsCard({ topMerchants }: { topMerchants: MerchantSpend[] }) {
  const top5     = topMerchants.slice(0, 5);
  const maxTotal = top5[0]?.total ?? 1;

  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4 shadow-sm flex flex-col gap-3">
      <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">Top Merchants</span>
      <div className="flex flex-col gap-2.5">
        {top5.map((m, i) => (
          <div key={m.name} className="flex items-center gap-2">
            <span className="text-xs text-gray-400 w-4 tabular-nums shrink-0">{i + 1}</span>
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between gap-1 mb-0.5">
                <span className="text-xs font-medium text-gray-800 dark:text-gray-200 truncate">{m.name}</span>
                <span className="text-xs tabular-nums text-gray-600 dark:text-gray-400 shrink-0">{gbp.format(m.total)}</span>
              </div>
              <div className="h-1 rounded-full bg-gray-100 dark:bg-gray-800 overflow-hidden">
                <div className="h-full rounded-full bg-blue-500" style={{ width: `${(m.total / maxTotal) * 100}%` }} />
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Card: Day of week pattern ─────────────────────────────────────────────────
function DayPatternCard({ byDayOfWeek }: { byDayOfWeek: DaySpend[] }) {
  const maxDay     = Math.max(...byDayOfWeek.map(d => d.total), 1);
  const totalSpend = byDayOfWeek.reduce((s, d) => s + d.total, 0);
  const peakDay    = byDayOfWeek.reduce((best, d) => d.total > best.total ? d : best, byDayOfWeek[0]);

  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4 shadow-sm flex flex-col gap-3">
      <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">Spend by Day</span>
      <div className="flex items-end gap-1.5 h-16">
        {byDayOfWeek.map((d) => {
          const pct       = totalSpend > 0 ? d.total / maxDay : 0;
          const isWeekend = d.day === "Sat" || d.day === "Sun";
          const isPeak    = d.day === peakDay?.day;
          return (
            <div key={d.day} className="flex-1 flex flex-col items-center gap-1">
              <div className="w-full flex items-end" style={{ height: 44 }}>
                <div
                  className={`w-full rounded-t transition-all ${
                    isPeak ? "bg-blue-500" : isWeekend ? "bg-indigo-300 dark:bg-indigo-700" : "bg-gray-300 dark:bg-gray-700"
                  }`}
                  style={{ height: `${Math.max(pct * 100, 4)}%` }}
                />
              </div>
              <span className={`text-[11px] font-medium ${isPeak ? "text-blue-500" : "text-gray-400"}`}>{d.day}</span>
            </div>
          );
        })}
      </div>
      {peakDay && (
        <p className="text-xs text-gray-400">
          You spend most on <span className="font-medium text-gray-700 dark:text-gray-300">{peakDay.day}s</span>
          {" — "}
          <span className="tabular-nums">{totalSpend > 0 ? ((peakDay.total / totalSpend) * 100).toFixed(0) : 0}%</span> of total
        </p>
      )}
    </div>
  );
}

// ── Main export (TopMerchants + DayPattern only) ──────────────────────────────
export default function SpendingInsights({
  topMerchants,
  byDayOfWeek,
}: {
  topMerchants: MerchantSpend[];
  byDayOfWeek: DaySpend[];
}) {
  return (
    <div>
      <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50 mb-3">Insights</h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <TopMerchantsCard topMerchants={topMerchants} />
        <DayPatternCard byDayOfWeek={byDayOfWeek} />
      </div>
    </div>
  );
}
