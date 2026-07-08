"use client";

import { useState } from "react";
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip,
  BarChart, Bar, Cell, PieChart, Pie, CartesianGrid,
} from "recharts";
import { type MonthlySpend, type DailySpend, type MerchantSpend, type ScheduledSpend, type SpendingRow } from "@/lib/queries";
import { CATEGORY_EMOJIS, getCategoryColor, lightenColor } from "@/lib/category-emojis";

const gbp    = new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP", maximumFractionDigits: 0 });
const gbpDec = new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP", maximumFractionDigits: 2 });
const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function daysInMonth(year: number, month: number) {
  return new Date(year, month, 0).getDate();
}

function monthShortLabel(m: string) {
  const [y, mm] = m.split("-");
  return `${MONTH_NAMES[Number(mm) - 1]} '${y.slice(2)}`;
}

function monthFullLabel(m: string) {
  const [y, mm] = m.split("-");
  return `${MONTH_NAMES[Number(mm) - 1]} ${y}`;
}

// ── Hero: This month with budget chart ────────────────────────────────────────
export function ThisMonthHero({ monthly, daily, budget, recurring }: { monthly: MonthlySpend[]; daily: DailySpend[]; budget: number; recurring: ScheduledSpend[] }) {
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
  const overBudget = spent > budget;

  // Cumulative daily spend for current month
  const dayMap: Record<number, number> = {};
  for (const d of daily) {
    if (d.date.startsWith(currentKey)) {
      const day = parseInt(d.date.slice(8, 10), 10);
      dayMap[day] = (dayMap[day] ?? 0) + d.total;
    }
  }

  // Fixed-date payments (mortgage, council tax, ...) clamped into this month's day range.
  const scheduled       = recurring.map(r => ({ ...r, day: Math.min(r.day, totalDays) }));
  const totalScheduled  = scheduled.reduce((s, r) => s + r.amount, 0);
  const flexibleBudget  = Math.max(0, budget - totalScheduled);
  const flexiblePerDay  = flexibleBudget / totalDays;

  // Lump-sum recurring payments (mortgage etc.) shouldn't be assumed to repeat daily —
  // split spend-to-date into scheduled vs flexible, mirroring the target-pace line above.
  const scheduledPaidToDate = scheduled.filter(r => r.day <= dayOfMonth).reduce((s, r) => s + r.amount, 0);
  const scheduledRemaining  = scheduled.filter(r => r.day > dayOfMonth).reduce((s, r) => s + r.amount, 0);
  const dailyRate = dayOfMonth > 0 ? Math.max(0, spent - scheduledPaidToDate) / dayOfMonth : 0;
  const projected = Math.round(spent + dailyRate * daysLeft + scheduledRemaining);
  const pctChange = lastTotal > 0 ? ((projected - lastTotal) / lastTotal) * 100 : null;

  // Both lines descend: budget → 0 (remaining budget left).
  // Target dips on scheduled payment days instead of assuming a flat daily burn.
  let cumul = 0;
  const chartData = Array.from({ length: totalDays }, (_, i) => {
    const day    = i + 1;
    const isDone = day <= dayOfMonth;
    if (isDone) cumul += dayMap[day] ?? 0;
    const scheduledDue = scheduled.filter(r => r.day <= day).reduce((s, r) => s + r.amount, 0);
    return {
      day: String(day),
      actual: isDone ? Math.round(budget - cumul) : null,
      target: Math.round(budget - scheduledDue - flexiblePerDay * day),
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

// ── Card: Top 10 merchants by total spend ──────────────────────────────────────
export function TopMerchantsCard({ topMerchants, monthly }: { topMerchants: MerchantSpend[]; monthly: MonthlySpend[] }) {
  const [excludeMortgage, setExcludeMortgage] = useState(false);
  const hasMortgage = topMerchants.some(m => m.category === "Mortgage");
  const filtered = excludeMortgage ? topMerchants.filter(m => m.category !== "Mortgage") : topMerchants;
  const top10    = filtered.slice(0, 10);
  const maxTotal = top10[0]?.total ?? 1;

  const sortedMonths = [...monthly].map(m => m.month).sort();
  const periodLabel = sortedMonths.length === 0
    ? ""
    : sortedMonths[0] === sortedMonths[sortedMonths.length - 1]
      ? monthFullLabel(sortedMonths[0])
      : `${monthFullLabel(sortedMonths[0])} – ${monthFullLabel(sortedMonths[sortedMonths.length - 1])}`;

  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4 sm:p-6 shadow-sm">
      <div className="flex items-center justify-between gap-3 mb-1">
        <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">Top 10 Merchants by Spend</h2>
        {hasMortgage && (
          <label className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 cursor-pointer select-none shrink-0">
            <input
              type="checkbox"
              checked={excludeMortgage}
              onChange={() => setExcludeMortgage(v => !v)}
              className="w-3.5 h-3.5 rounded accent-blue-500"
            />
            Exclude Mortgage
          </label>
        )}
      </div>
      {periodLabel && (
        <p className="text-xs text-gray-400 dark:text-gray-500 mb-4">All transactions, {periodLabel}</p>
      )}
      <div className="flex flex-col gap-2.5">
        {top10.map((m, i) => (
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

// ── Card: Avg Monthly Spend by Category (period-over-period comparison) ───────
type YoYRow = { cat: string; aAvg: number; bAvg: number; aTotal: number; bTotal: number };
type PeriodPreset = { id: string; label: string; periodA: string[]; periodB: string[]; labelA: string; labelB: string };

function rangeLabel(monthsArr: string[]): string {
  if (monthsArr.length === 0) return "";
  return monthsArr.length === 1
    ? monthShortLabel(monthsArr[0])
    : `${monthShortLabel(monthsArr[0])}–${monthShortLabel(monthsArr[monthsArr.length - 1])}`;
}

// Builds the set of selectable comparison presets that actually have enough
// history behind them — a preset only appears once both periods it needs
// are fully available, so "Last 12 months" quietly shows up once a year
// of data has accumulated instead of comparing against a half-empty period.
function buildPresets(completeMonths: string[]): PeriodPreset[] {
  const presets: PeriodPreset[] = [];

  if (completeMonths.length > 0) {
    const currentYear = completeMonths[completeMonths.length - 1].slice(0, 4);
    const prevYear    = String(Number(currentYear) - 1);
    const monthNums   = completeMonths.filter(m => m.startsWith(currentYear)).map(m => m.slice(5, 7));
    const sharedNums  = monthNums.filter(mm => completeMonths.includes(`${prevYear}-${mm}`));
    if (sharedNums.length > 0) {
      const periodA = sharedNums.map(mm => `${prevYear}-${mm}`);
      const periodB = sharedNums.map(mm => `${currentYear}-${mm}`);
      presets.push({ id: "ytd", label: "Year to date", periodA, periodB, labelA: rangeLabel(periodA), labelB: rangeLabel(periodB) });
    }
  }

  if (completeMonths.length >= 12) {
    const periodB = completeMonths.slice(-6);
    const periodA = completeMonths.slice(-12, -6);
    presets.push({ id: "6mo", label: "Last 6 months", periodA, periodB, labelA: rangeLabel(periodA), labelB: rangeLabel(periodB) });
  }

  if (completeMonths.length >= 24) {
    const periodB = completeMonths.slice(-12);
    const periodA = completeMonths.slice(-24, -12);
    presets.push({ id: "12mo", label: "Last 12 months", periodA, periodB, labelA: rangeLabel(periodA), labelB: rangeLabel(periodB) });
  }

  return presets;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function BehaviourBarTip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const row: YoYRow = payload[0].payload;
  const delta = row.aAvg > 0 ? ((row.bAvg - row.aAvg) / row.aAvg) * 100 : null;
  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-lg p-3 text-xs">
      <div className="font-semibold mb-1.5 text-gray-800 dark:text-gray-200">
        {CATEGORY_EMOJIS[row.cat] ?? "📦"} {row.cat}
      </div>
      <div className="flex justify-between gap-3 text-gray-500 dark:text-gray-400">
        <span>Earlier period avg/mo</span>
        <span className="font-medium text-gray-800 dark:text-gray-200">{gbp.format(row.aAvg)}</span>
      </div>
      <div className="flex justify-between gap-3 text-gray-500 dark:text-gray-400">
        <span>Later period avg/mo</span>
        <span className="font-medium text-gray-800 dark:text-gray-200">{gbp.format(row.bAvg)}</span>
      </div>
      {delta != null && (
        <div className="mt-1 pt-1 border-t border-gray-100 dark:border-gray-800 flex justify-between font-semibold">
          <span className="text-gray-600 dark:text-gray-400">Change</span>
          <span className={delta > 0 ? "text-red-500 dark:text-red-400" : "text-emerald-600 dark:text-emerald-400"}>
            {delta > 0 ? "+" : ""}{delta.toFixed(0)}%
          </span>
        </div>
      )}
    </div>
  );
}

export function SpendingBehaviourChangeCard({ byCategory }: { byCategory: SpendingRow[] }) {
  const [chartType, setChartType] = useState<"bars" | "pie">("bars");
  const [presetId, setPresetId]   = useState<string | null>(null);

  const months = [...new Set(byCategory.map(r => r.month))].sort();
  const now = new Date();
  const todayMonthKey = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  // Exclude the current, still-accumulating month from every comparison —
  // including it drags "this period"'s average down for no real reason
  // (e.g. a fixed monthly bill that simply hasn't posted yet this month).
  const completeMonths = months.filter(m => m !== todayMonthKey);

  const presets      = buildPresets(completeMonths);
  const activePreset = presets.find(p => p.id === presetId) ?? presets[0];

  if (!activePreset) {
    return (
      <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4 sm:p-6 shadow-sm">
        <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50 mb-1">Avg Monthly Spend by Category</h2>
        <p className="text-xs text-gray-400">Need at least two comparable months of history to show this.</p>
      </div>
    );
  }

  const totals: Record<string, { a: number; b: number }> = {};
  for (const row of byCategory) {
    if (activePreset.periodA.includes(row.month)) {
      (totals[row.category] ??= { a: 0, b: 0 }).a += row.total;
    } else if (activePreset.periodB.includes(row.month)) {
      (totals[row.category] ??= { a: 0, b: 0 }).b += row.total;
    }
  }

  const nA = activePreset.periodA.length;
  const nB = activePreset.periodB.length;
  const rows: YoYRow[] = Object.entries(totals)
    .map(([cat, v]) => ({ cat, aAvg: v.a / nA, bAvg: v.b / nB, aTotal: v.a, bTotal: v.b }))
    .filter(r => r.aTotal > 0 || r.bTotal > 0)
    .sort((a, b) => (b.aTotal + b.bTotal) - (a.aTotal + a.bTotal))
    .slice(0, 7);

  const aPieTotal = rows.reduce((s, r) => s + r.aAvg, 0);
  const bPieTotal = rows.reduce((s, r) => s + r.bAvg, 0);

  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4 sm:p-6 shadow-sm">
      <div className="flex items-center justify-between gap-3 mb-3">
        <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">Avg Monthly Spend by Category</h2>
        <div className="flex items-center gap-0.5 bg-gray-100 dark:bg-gray-800 rounded-md p-0.5 shrink-0">
          {(["bars", "pie"] as const).map(t => (
            <button
              key={t}
              onClick={() => setChartType(t)}
              className={`px-2.5 py-1 text-xs font-medium rounded transition-colors ${
                chartType === t
                  ? "bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-50 shadow-sm"
                  : "text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-50"
              }`}
            >
              {t === "bars" ? "Bars" : "Pie"}
            </button>
          ))}
        </div>
      </div>

      {presets.length > 1 && (
        <div className="flex flex-wrap items-center gap-1.5 mb-2">
          {presets.map(p => (
            <button
              key={p.id}
              onClick={() => setPresetId(p.id)}
              className={`px-2.5 py-1 text-xs font-medium rounded-md transition-colors ${
                activePreset.id === p.id
                  ? "bg-gray-800 dark:bg-gray-100 text-white dark:text-gray-900"
                  : "bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-50"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      )}

      <p className="text-[11px] text-gray-400 dark:text-gray-500 mb-3">
        <span className="text-gray-500 dark:text-gray-400">{activePreset.labelA}</span> vs{" "}
        <span className="font-medium text-gray-600 dark:text-gray-400">{activePreset.labelB}</span>
      </p>

      {chartType === "bars" ? (
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={rows} margin={{ top: 4, right: 4, left: 0, bottom: 4 }} barGap={2}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-gray-100 dark:stroke-gray-800" vertical={false} />
            <XAxis
              dataKey="cat"
              tick={{ fontSize: 13 }}
              tickFormatter={cat => CATEGORY_EMOJIS[cat] ?? "📦"}
              tickLine={false}
              axisLine={false}
              interval={0}
            />
            <YAxis
              tick={{ fontSize: 11, fill: "currentColor" }}
              tickLine={false}
              axisLine={false}
              tickFormatter={v => `£${(v / 1000).toFixed(1)}k`}
              width={42}
            />
            <Tooltip content={<BehaviourBarTip />} cursor={{ fill: "rgba(0,0,0,0.03)" }} />
            <Bar dataKey="aAvg" radius={[3, 3, 0, 0]}>
              {rows.map(r => <Cell key={r.cat} fill={lightenColor(getCategoryColor(r.cat), 0.55)} />)}
            </Bar>
            <Bar dataKey="bAvg" radius={[3, 3, 0, 0]}>
              {rows.map(r => <Cell key={r.cat} fill={getCategoryColor(r.cat)} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      ) : (
        <div className="grid grid-cols-2 gap-2">
          {[
            { label: activePreset.labelA, total: aPieTotal, key: "aAvg" as const, tint: 0.55 },
            { label: activePreset.labelB, total: bPieTotal, key: "bAvg" as const, tint: 0 },
          ].map(pie => (
            <div key={pie.label} className="relative h-36">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={rows}
                    dataKey={pie.key}
                    nameKey="cat"
                    innerRadius="55%"
                    outerRadius="90%"
                    stroke="none"
                    paddingAngle={2}
                    isAnimationActive={false}
                  >
                    {rows.map(r => (
                      <Cell key={r.cat} fill={pie.tint > 0 ? lightenColor(getCategoryColor(r.cat), pie.tint) : getCategoryColor(r.cat)} />
                    ))}
                  </Pie>
                  <Tooltip
                    // eslint-disable-next-line @typescript-eslint/no-explicit-any
                    formatter={(v: any, _n: any, p: any) => [gbp.format(Number(v)), p?.payload?.cat]}
                    contentStyle={{ fontSize: 12, borderRadius: 10, border: "1px solid rgba(0,0,0,0.08)" }}
                  />
                </PieChart>
              </ResponsiveContainer>
              <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center px-2">
                <div className="text-[10px] uppercase tracking-wide text-gray-400 dark:text-gray-500 text-center leading-tight">{pie.label}</div>
                <div className="text-sm font-semibold tabular-nums text-gray-900 dark:text-gray-50">
                  {gbp.format(pie.total)}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Legend with per-category change */}
      <div className="mt-3 space-y-1.5">
        {rows.map(r => {
          const delta = r.aAvg > 0 ? ((r.bAvg - r.aAvg) / r.aAvg) * 100 : null;
          return (
            <div key={r.cat} className="flex items-center gap-2 text-xs">
              <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ backgroundColor: getCategoryColor(r.cat) }} />
              <span className="text-gray-700 dark:text-gray-300 w-28 shrink-0 truncate">
                {CATEGORY_EMOJIS[r.cat] ?? "📦"} {r.cat}
              </span>
              <span className="text-gray-400 dark:text-gray-500 tabular-nums flex-1 text-right">{gbp.format(r.aAvg)}</span>
              <span className="text-gray-300 dark:text-gray-600">→</span>
              <span className="text-gray-700 dark:text-gray-300 tabular-nums w-16 text-right">{gbp.format(r.bAvg)}</span>
              <span className={`tabular-nums w-12 text-right font-medium ${
                delta == null ? "text-gray-400" : delta > 0 ? "text-red-500 dark:text-red-400" : "text-emerald-600 dark:text-emerald-400"
              }`}>
                {delta == null ? "—" : `${delta > 0 ? "+" : ""}${delta.toFixed(0)}%`}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
