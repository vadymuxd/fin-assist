"use client";

import { useMemo } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { MortgageSnapshot } from "@/lib/queries";

const ORIGINAL_BALANCE = 570999;

const gbp = new Intl.NumberFormat("en-GB", {
  style: "currency",
  currency: "GBP",
  maximumFractionDigits: 0,
});

function shortDate(iso: string) {
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-GB", {
    month: "short",
    year: "2-digit",
    timeZone: "UTC",
  });
}

type TooltipPayloadItem = { value?: number | string | (number | string)[]; name?: string; color?: string };

function SplitTooltip({
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
      {payload.map((p, i) => (
        <div key={i} className="flex items-center gap-2 mt-0.5">
          <span className="w-2 h-2 rounded-full" style={{ backgroundColor: p.color }} />
          <span className="text-gray-500 dark:text-gray-400">{p.name}:</span>
          <span className="font-medium tabular-nums text-gray-900 dark:text-gray-50">
            {gbp.format(Number(Array.isArray(p.value) ? p.value[0] ?? 0 : p.value ?? 0))}
          </span>
        </div>
      ))}
    </div>
  );
}

function LtvTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: readonly TooltipPayloadItem[];
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  const val = Number(Array.isArray(payload[0]?.value) ? payload[0]?.value[0] ?? 0 : payload[0]?.value ?? 0);
  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white/95 dark:bg-gray-900/95 backdrop-blur p-3 shadow-lg text-xs">
      <div className="font-medium text-gray-900 dark:text-gray-50 mb-1.5">
        {typeof label === "string" ? shortDate(label) : ""}
      </div>
      <div className="flex items-center gap-2">
        <span className="w-2 h-2 rounded-full bg-indigo-500" />
        <span className="font-medium tabular-nums text-gray-900 dark:text-gray-50">{val.toFixed(1)}%</span>
      </div>
    </div>
  );
}

export default function MortgageMetrics({ snapshots }: { snapshots: MortgageSnapshot[] }) {
  const splitRows = useMemo(() =>
    snapshots.map((s) => {
      const interest = s.balance * (s.rate / 12);
      const principal = s.monthly_payment - interest;
      return { date: s.date, interest: Math.round(interest), principal: Math.round(principal) };
    }),
  [snapshots]);

  const ltvRows = useMemo(() =>
    snapshots.map((s) => ({
      date: s.date,
      ltv: parseFloat(((s.balance / s.property_value) * 100).toFixed(2)),
    })),
  [snapshots]);

  const latest = snapshots.at(-1);
  const paid = latest ? ORIGINAL_BALANCE - latest.balance : 0;
  const paidPct = latest ? (paid / ORIGINAL_BALANCE) * 100 : 0;
  const remainingPct = 100 - paidPct;

  if (snapshots.length < 2) return null;

  return (
    <div className="space-y-4">
      {/* Interest vs Principal split */}
      <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4 sm:p-6 shadow-sm">
        <div className="mb-4">
          <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">Interest vs Principal</h2>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">Monthly payment breakdown over time</p>
        </div>
        <div className="h-56 sm:h-72 -ml-2">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={splitRows} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="interestFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#f97316" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="#f97316" stopOpacity={0.05} />
                </linearGradient>
                <linearGradient id="principalFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#10b981" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="#10b981" stopOpacity={0.05} />
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
                minTickGap={40}
              />
              <YAxis
                tick={{ fontSize: 11, fill: "currentColor" }}
                className="text-gray-400 dark:text-gray-500"
                tickLine={false}
                axisLine={false}
                tickFormatter={(v) => gbp.format(v)}
                width={64}
              />
              <Tooltip
                content={(props) => (
                  <SplitTooltip
                    active={props.active}
                    payload={props.payload as readonly TooltipPayloadItem[] | undefined}
                    label={props.label as string | undefined}
                  />
                )}
                cursor={{ stroke: "#94a3b8", strokeDasharray: "3 3" }}
              />
              <Area
                type="monotone"
                dataKey="interest"
                name="Interest"
                stroke="#f97316"
                strokeWidth={2}
                fill="url(#interestFill)"
                dot={false}
                activeDot={{ r: 3 }}
                isAnimationActive={false}
              />
              <Area
                type="monotone"
                dataKey="principal"
                name="Principal"
                stroke="#10b981"
                strokeWidth={2}
                fill="url(#principalFill)"
                dot={false}
                activeDot={{ r: 3 }}
                isAnimationActive={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        <div className="flex items-center gap-4 mt-2">
          <div className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400">
            <span className="w-3 h-0.5 rounded bg-orange-500 inline-block" />
            Interest (decreasing)
          </div>
          <div className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400">
            <span className="w-3 h-0.5 rounded bg-emerald-500 inline-block" />
            Principal (increasing)
          </div>
        </div>
      </div>

      {/* LTV trend */}
      <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4 sm:p-6 shadow-sm">
        <div className="mb-4">
          <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">LTV Trend</h2>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">Loan-to-value ratio as balance decreases</p>
        </div>
        <div className="h-48 sm:h-64 -ml-2">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={ltvRows} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="ltvFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#6366f1" stopOpacity={0.2} />
                  <stop offset="100%" stopColor="#6366f1" stopOpacity={0} />
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
                minTickGap={40}
              />
              <YAxis
                tick={{ fontSize: 11, fill: "currentColor" }}
                className="text-gray-400 dark:text-gray-500"
                tickLine={false}
                axisLine={false}
                tickFormatter={(v) => `${v}%`}
                width={44}
                domain={["dataMin - 1", "dataMax + 1"]}
              />
              <Tooltip
                content={(props) => (
                  <LtvTooltip
                    active={props.active}
                    payload={props.payload as readonly TooltipPayloadItem[] | undefined}
                    label={props.label as string | undefined}
                  />
                )}
                cursor={{ stroke: "#94a3b8", strokeDasharray: "3 3" }}
              />
              <Line
                type="monotone"
                dataKey="ltv"
                name="LTV"
                stroke="#6366f1"
                strokeWidth={2.25}
                dot={false}
                activeDot={{ r: 4 }}
                isAnimationActive={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Payoff progress */}
      <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4 sm:p-6 shadow-sm">
        <div className="mb-4">
          <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">Payoff Progress</h2>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
            {gbp.format(paid)} repaid of {gbp.format(ORIGINAL_BALANCE)} original balance
          </p>
        </div>
        <div className="space-y-3">
          <div className="h-4 rounded-full bg-gray-100 dark:bg-gray-800 overflow-hidden">
            <div
              className="h-full rounded-full bg-gradient-to-r from-orange-400 to-emerald-400 transition-all"
              style={{ width: `${paidPct}%` }}
            />
          </div>
          <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-gradient-to-br from-orange-400 to-emerald-400 inline-block" />
              <span className="font-medium text-gray-700 dark:text-gray-300">{paidPct.toFixed(1)}%</span>
              <span>paid off</span>
            </div>
            <div className="text-right">
              <span className="font-medium text-rose-600 dark:text-rose-400">{remainingPct.toFixed(1)}%</span>
              <span className="ml-1">remaining ({gbp.format(latest?.balance ?? 0)})</span>
            </div>
          </div>
        </div>

        {latest && (
          <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-3 pt-4 border-t border-gray-100 dark:border-gray-800">
            <div>
              <div className="text-[10px] uppercase tracking-wide text-gray-400 dark:text-gray-500">Original</div>
              <div className="text-sm font-semibold tabular-nums text-gray-700 dark:text-gray-300">{gbp.format(ORIGINAL_BALANCE)}</div>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-wide text-gray-400 dark:text-gray-500">Paid Off</div>
              <div className="text-sm font-semibold tabular-nums text-emerald-600 dark:text-emerald-400">{gbp.format(paid)}</div>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-wide text-gray-400 dark:text-gray-500">Remaining</div>
              <div className="text-sm font-semibold tabular-nums text-rose-600 dark:text-rose-400">{gbp.format(latest.balance)}</div>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-wide text-gray-400 dark:text-gray-500">Lender</div>
              <div className="text-sm font-medium tabular-nums text-gray-700 dark:text-gray-300">{latest.lender}</div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
