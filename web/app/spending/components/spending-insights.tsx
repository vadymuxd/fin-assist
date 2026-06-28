"use client";

import { type MonthlySpend, type MerchantSpend, type DaySpend } from "@/lib/queries";

type Props = {
  monthly: MonthlySpend[];
  topMerchants: MerchantSpend[];
  byDayOfWeek: DaySpend[];
};

const gbp = new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP", maximumFractionDigits: 0 });
const gbpDec = new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP", maximumFractionDigits: 2 });

function currentAndLastMonth(monthly: MonthlySpend[]): { current: MonthlySpend | null; last: MonthlySpend | null } {
  const now = new Date();
  const cm = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  const prev = now.getMonth() === 0
    ? `${now.getFullYear() - 1}-12`
    : `${now.getFullYear()}-${String(now.getMonth()).padStart(2, "0")}`;
  return {
    current: monthly.find(m => m.month === cm) ?? null,
    last:    monthly.find(m => m.month === prev) ?? null,
  };
}

function daysInMonth(year: number, month: number) {
  return new Date(year, month, 0).getDate();
}

// ── Card: This month so far ───────────────────────────────────────────────────
function MonthPaceCard({ monthly }: { monthly: MonthlySpend[] }) {
  const { current, last } = currentAndLastMonth(monthly);
  const now = new Date();
  const dayOfMonth = now.getDate();
  const totalDays = daysInMonth(now.getFullYear(), now.getMonth() + 1);
  const daysLeft = totalDays - dayOfMonth;

  const spent = current?.total ?? 0;
  const dailyRate = dayOfMonth > 0 ? spent / dayOfMonth : 0;
  const projected = dailyRate * totalDays;
  const lastTotal = last?.total ?? 0;
  const pctChange = lastTotal > 0 ? ((projected - lastTotal) / lastTotal) * 100 : null;

  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-950 p-4 flex flex-col gap-3">
      <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">This Month</span>
      <div>
        <div className="text-2xl font-bold text-gray-900 dark:text-gray-50 tabular-nums">
          {gbp.format(spent)}
        </div>
        <div className="text-xs text-gray-400 mt-0.5">
          {daysLeft} days left · {gbpDec.format(dailyRate)}/day
        </div>
      </div>
      <div className="text-xs text-gray-500 dark:text-gray-400 space-y-1">
        <div className="flex justify-between">
          <span>Projected total</span>
          <span className="tabular-nums text-gray-700 dark:text-gray-300 font-medium">{gbp.format(projected)}</span>
        </div>
        {lastTotal > 0 && (
          <div className="flex justify-between">
            <span>Last month</span>
            <span className={`tabular-nums font-medium ${
              pctChange != null && pctChange > 0
                ? "text-red-500 dark:text-red-400"
                : "text-emerald-600 dark:text-emerald-400"
            }`}>
              {gbp.format(lastTotal)}
              {pctChange != null && (
                <span className="ml-1 text-[10px]">
                  ({pctChange > 0 ? "+" : ""}{pctChange.toFixed(0)}% proj)
                </span>
              )}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Card: Top merchants ───────────────────────────────────────────────────────
function TopMerchantsCard({ topMerchants }: { topMerchants: MerchantSpend[] }) {
  const top5 = topMerchants.slice(0, 5);
  const maxTotal = top5[0]?.total ?? 1;

  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-950 p-4 flex flex-col gap-3">
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
                <div
                  className="h-full rounded-full bg-blue-500"
                  style={{ width: `${(m.total / maxTotal) * 100}%` }}
                />
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
  const maxDay = Math.max(...byDayOfWeek.map(d => d.total), 1);
  const totalSpend = byDayOfWeek.reduce((s, d) => s + d.total, 0);
  const peakDay = byDayOfWeek.reduce((best, d) => d.total > best.total ? d : best, byDayOfWeek[0]);

  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-950 p-4 flex flex-col gap-3">
      <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">Spend by Day</span>
      <div className="flex items-end gap-1.5 h-16">
        {byDayOfWeek.map((d) => {
          const pct = totalSpend > 0 ? d.total / maxDay : 0;
          const isWeekend = d.day === "Sat" || d.day === "Sun";
          const isPeak = d.day === peakDay?.day;
          return (
            <div key={d.day} className="flex-1 flex flex-col items-center gap-1">
              <div className="w-full flex items-end" style={{ height: 44 }}>
                <div
                  className={`w-full rounded-t transition-all ${
                    isPeak
                      ? "bg-blue-500"
                      : isWeekend
                      ? "bg-indigo-300 dark:bg-indigo-700"
                      : "bg-gray-300 dark:bg-gray-700"
                  }`}
                  style={{ height: `${Math.max(pct * 100, 4)}%` }}
                />
              </div>
              <span className={`text-[9px] font-medium ${isPeak ? "text-blue-500" : "text-gray-400"}`}>{d.day}</span>
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

// ── Main export ───────────────────────────────────────────────────────────────
export default function SpendingInsights({ monthly, topMerchants, byDayOfWeek }: Props) {
  return (
    <div>
      <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">Insights</h2>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <MonthPaceCard monthly={monthly} />
        <TopMerchantsCard topMerchants={topMerchants} />
        <DayPatternCard byDayOfWeek={byDayOfWeek} />
      </div>
    </div>
  );
}
