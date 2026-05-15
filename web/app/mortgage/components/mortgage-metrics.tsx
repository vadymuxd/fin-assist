"use client";

import { useMemo } from "react";
import {
  CartesianGrid,
  ComposedChart,
  Area,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { MortgageSnapshot } from "@/lib/queries";
import {
  generateHalifaxSchedule,
  HALIFAX_LOAN,
  COOP_LOAN,
  DEPOSIT,
  MORTGAGE_START,
  MORTGAGE_TERM_YEARS,
} from "@/lib/queries";

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
  const firstCoopDate = snapshots[0]?.date ?? "9999-01-01";
  const latest = snapshots.at(-1);

  const halifaxSchedule = useMemo(
    () => generateHalifaxSchedule(firstCoopDate),
    [firstCoopDate],
  );

  const splitRows = useMemo(() => {
    const halifaxPart = halifaxSchedule.map((h) => ({
      date: h.date,
      interest: h.interest,
      principal: h.principal,
    }));
    const coopPart = snapshots.map((s) => {
      const interest = s.balance * (s.rate / 12);
      const principal = s.monthly_payment - interest;
      return { date: s.date, interest: Math.round(interest), principal: Math.round(principal) };
    });
    return [...halifaxPart, ...coopPart];
  }, [halifaxSchedule, snapshots]);

  const ltvRows = useMemo(() => {
    const halifaxPart = halifaxSchedule.map((h) => ({
      date: h.date,
      ltv: h.ltv,
    }));
    const coopPart = snapshots.map((s) => ({
      date: s.date,
      ltv: parseFloat(((s.balance / s.property_value) * 100).toFixed(2)),
    }));
    return [...halifaxPart, ...coopPart];
  }, [halifaxSchedule, snapshots]);

  const halifaxEndBalance = halifaxSchedule.at(-1)?.balance ?? HALIFAX_LOAN;
  const halifaxPaid = HALIFAX_LOAN - halifaxEndBalance;

  const coopPaid = latest ? COOP_LOAN - latest.balance : 0;
  const coopPaidPct = (coopPaid / COOP_LOAN) * 100;

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

      {/* ── Tile: Current Deal ────────────────────────────────── */}
      {latest && (() => {
        const startFmt = new Date(`${firstCoopDate}T00:00:00Z`).toLocaleDateString("en-GB", {
          month: "short", year: "numeric", timeZone: "UTC",
        });
        return (
          <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4 sm:p-6 shadow-sm">
            <div className="flex items-start justify-between gap-4 mb-4">
              <div>
                <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">Current Deal</h2>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                  {latest.lender} · since {startFmt}
                </p>
              </div>
              <div className="text-right shrink-0">
                <div className="text-[10px] uppercase tracking-wide text-gray-400 dark:text-gray-500">Balance</div>
                <div className="text-lg font-semibold tabular-nums text-rose-600 dark:text-rose-400">{gbp.format(latest.balance)}</div>
              </div>
            </div>

            {/* Co-op payoff bar */}
            <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400 mb-1.5">
              <span>
                Paid off:{" "}
                <span className="font-semibold text-blue-600 dark:text-blue-400">{gbp.format(coopPaid)}</span>
                <span className="ml-1 text-gray-400">({coopPaidPct.toFixed(1)}%)</span>
              </span>
              <span>Started at {gbp.format(COOP_LOAN)}</span>
            </div>
            <div className="h-3 rounded-full bg-gray-100 dark:bg-gray-800 overflow-hidden">
              <div
                className="h-full rounded-full bg-blue-500"
                style={{ width: `${coopPaidPct}%` }}
              />
            </div>

            {/* Stats row */}
            <div className="mt-4 pt-4 border-t border-gray-100 dark:border-gray-800 grid grid-cols-3 gap-3">
              <div>
                <div className="text-[10px] uppercase tracking-wide text-gray-400 dark:text-gray-500">Rate</div>
                <div className="text-sm font-semibold tabular-nums text-gray-700 dark:text-gray-300">
                  {(latest.rate * 100).toFixed(2)}%
                </div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-wide text-gray-400 dark:text-gray-500">Monthly</div>
                <div className="text-sm font-semibold tabular-nums text-gray-700 dark:text-gray-300">
                  {gbp.format(latest.monthly_payment)}
                </div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-wide text-gray-400 dark:text-gray-500">Halifax paid off</div>
                <div className="text-sm font-semibold tabular-nums text-orange-500 dark:text-orange-400">
                  {gbp.format(halifaxPaid)}
                </div>
              </div>
            </div>
          </div>
        );
      })()}

      {/* ── Tile: Mortgage Journey ─────────────────────────────── */}
      {latest && (() => {
        const propertyValue = latest.property_value;
        const msStart = new Date(`${MORTGAGE_START}T00:00:00Z`);
        const msEnd = new Date(msStart);
        msEnd.setFullYear(msEnd.getFullYear() + MORTGAGE_TERM_YEARS);
        const now = new Date();
        const totalMs = msEnd.getTime() - msStart.getTime();
        const elapsedMs = Math.min(now.getTime() - msStart.getTime(), totalMs);
        const yearsElapsed = elapsedMs / (1000 * 60 * 60 * 24 * 365.25);
        const yearsRemaining = Math.max(0, MORTGAGE_TERM_YEARS - yearsElapsed);
        const timePct = (yearsElapsed / MORTGAGE_TERM_YEARS) * 100;

        const endFmt = msEnd.toLocaleDateString("en-GB", { month: "short", year: "numeric" });
        const startFmt = msStart.toLocaleDateString("en-GB", { month: "short", year: "numeric" });

        const depositPct  = (DEPOSIT     / propertyValue) * 100;
        const halifaxPct  = (halifaxPaid / propertyValue) * 100;
        const coopPaidPct2 = (coopPaid   / propertyValue) * 100;

        const midFmt = new Date(
          (msStart.getTime() + msEnd.getTime()) / 2,
        ).toLocaleDateString("en-GB", { month: "short", year: "numeric" });

        function Legend({ color, label, value }: { color: string; label: string; value: string }) {
          return (
            <span className="inline-flex items-baseline gap-1 text-[11px]">
              <span className={`inline-block w-2.5 h-2.5 rounded-sm ${color} shrink-0 self-center`} />
              <span className="text-gray-500 dark:text-gray-400">{label}</span>
              <span className="font-semibold tabular-nums text-gray-700 dark:text-gray-300">{value}</span>
            </span>
          );
        }

        return (
          <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4 sm:p-6 shadow-sm">
            <div className="flex items-start justify-between gap-3 mb-5">
              <div>
                <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">Mortgage Journey</h2>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                  {startFmt} → {endFmt} · {MORTGAGE_TERM_YEARS} years
                </p>
              </div>
              <div className="text-right shrink-0">
                <div className="text-[10px] uppercase tracking-wide text-gray-400 dark:text-gray-500">LTV</div>
                <div className="text-lg font-semibold tabular-nums text-gray-700 dark:text-gray-300">
                  {((latest.balance / propertyValue) * 100).toFixed(1)}%
                </div>
              </div>
            </div>

            {/* ── Money bar ── */}
            <div className="mb-5">
              <div className="flex justify-between text-[10px] text-gray-400 dark:text-gray-500 mb-1.5">
                <span>£0</span>
                <span>{gbp.format(propertyValue / 2)}</span>
                <span>{gbp.format(propertyValue)}</span>
              </div>
              <div className="relative h-7 rounded-lg bg-gray-100 dark:bg-gray-800 overflow-hidden flex">
                {/* Deposit */}
                <div
                  className="h-full bg-slate-400 dark:bg-slate-500 flex items-center justify-center"
                  style={{ width: `${depositPct}%` }}
                  title={`Deposit ${gbp.format(DEPOSIT)}`}
                />
                {/* Halifax paid */}
                <div
                  className="h-full bg-orange-400 flex items-center justify-center"
                  style={{ width: `${halifaxPct}%` }}
                  title={`Halifax paid ${gbp.format(halifaxPaid)}`}
                />
                {/* Co-op paid */}
                <div
                  className="h-full bg-blue-500 flex items-center justify-center"
                  style={{ width: `${coopPaidPct2}%` }}
                  title={`Co-op paid ${gbp.format(coopPaid)}`}
                />
                {/* Remaining is the bar background */}
              </div>
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-2">
                <Legend color="bg-slate-400 dark:bg-slate-500" label="Deposit" value={gbp.format(DEPOSIT)} />
                <Legend color="bg-orange-400" label="Halifax" value={gbp.format(halifaxPaid)} />
                <Legend color="bg-blue-500" label="Co-op" value={gbp.format(coopPaid)} />
                <Legend color="bg-gray-200 dark:bg-gray-700" label="Remaining" value={gbp.format(latest.balance)} />
              </div>
            </div>

            {/* ── Time bar ── */}
            <div>
              <div className="flex justify-between text-[10px] text-gray-400 dark:text-gray-500 mb-1.5">
                <span>{startFmt}</span>
                <span>{midFmt}</span>
                <span>{endFmt}</span>
              </div>
              <div className="h-3 rounded-full bg-gray-100 dark:bg-gray-800 overflow-hidden" suppressHydrationWarning>
                <div
                  className="h-full rounded-full bg-indigo-400"
                  style={{ width: `${timePct}%` }}
                  suppressHydrationWarning
                />
              </div>
              <div className="flex justify-between text-[10px] mt-1.5" suppressHydrationWarning>
                <span className="text-indigo-500 dark:text-indigo-400 font-medium" suppressHydrationWarning>
                  {yearsElapsed.toFixed(1)} yrs elapsed
                </span>
                <span className="text-gray-400 dark:text-gray-500" suppressHydrationWarning>
                  {yearsRemaining.toFixed(1)} yrs remaining
                </span>
              </div>
            </div>
          </div>
        );
      })()}
    </div>
  );
}
