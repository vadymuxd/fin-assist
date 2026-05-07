"use client";

import { useMemo, useState } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { MortgageSnapshot } from "@/lib/queries";
import { generateHalifaxSchedule, HALIFAX_PROPERTY } from "@/lib/queries";

type Mode = "balance" | "equity";

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

type TooltipPayloadItem = { value?: number | string | (number | string)[]; name?: string };

function CustomTooltip({
  active,
  payload,
  label,
  mode,
}: {
  active?: boolean;
  payload?: readonly TooltipPayloadItem[];
  label?: string;
  mode: Mode;
}) {
  if (!active || !payload?.length) return null;
  const val = Number(Array.isArray(payload[0]?.value) ? payload[0]?.value[0] ?? 0 : payload[0]?.value ?? 0);
  const color = mode === "balance" ? "bg-orange-500" : "bg-emerald-500";
  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white/95 dark:bg-gray-900/95 backdrop-blur p-3 shadow-lg text-xs">
      <div className="font-medium text-gray-900 dark:text-gray-50 mb-1.5">
        {typeof label === "string" ? shortDate(label) : ""}
      </div>
      <div className="flex items-center gap-2">
        <span className={`w-2 h-2 rounded-full ${color}`} />
        <span className="font-medium tabular-nums text-gray-900 dark:text-gray-50">{gbp.format(val)}</span>
      </div>
    </div>
  );
}

export default function MortgageChart({ snapshots }: { snapshots: MortgageSnapshot[] }) {
  const [mode, setMode] = useState<Mode>("balance");
  const [half, setHalf] = useState(false);

  const combined = useMemo(() => {
    const firstCoopDate = snapshots[0]?.date ?? "9999-01-01";
    const halifaxRows = generateHalifaxSchedule(firstCoopDate).map((h) => ({
      date: h.date,
      balance: h.balance,
      equity: HALIFAX_PROPERTY - h.balance,
      equity_half: (HALIFAX_PROPERTY - h.balance) / 2,
    }));
    const coopRows = snapshots.map((s) => ({
      date: s.date,
      balance: s.balance,
      equity: s.equity,
      equity_half: s.equity_half,
    }));
    return [...halifaxRows, ...coopRows];
  }, [snapshots]);

  const rows = useMemo(
    () =>
      combined.map((s) => ({
        date: s.date,
        value:
          mode === "balance"
            ? half
              ? s.balance / 2
              : s.balance
            : half
              ? s.equity_half
              : s.equity,
      })),
    [combined, mode, half],
  );

  const isBalance = mode === "balance";
  const stroke = isBalance ? "#f97316" : "#10b981";
  const gradientId = isBalance ? "mortgageBalanceFill" : "mortgageEquityFill";
  const gradientColor = isBalance ? "#f97316" : "#10b981";
  const domain: [string, string] = isBalance
    ? ["dataMin - 5000", "dataMax + 5000"]
    : ["dataMin - 2000", "dataMax + 2000"];

  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4 sm:p-6 shadow-sm">
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 mb-4">
        <div>
          <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">
            {isBalance ? "Balance Repayment" : "Equity Growth"}
          </h2>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
            {isBalance ? "Outstanding mortgage balance over time" : "Home equity accumulated over time"}
            {half ? " (your ½)" : " (full)"}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-0.5 bg-gray-100 dark:bg-gray-800 rounded-md p-0.5">
            {(["balance", "equity"] as Mode[]).map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={`px-2.5 py-1 text-xs font-medium rounded transition-colors ${
                  mode === m
                    ? "bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-50 shadow-sm"
                    : "text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-50"
                }`}
              >
                {m === "balance" ? "Balance" : "Equity"}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-0.5 bg-gray-100 dark:bg-gray-800 rounded-md p-0.5">
            {([false, true] as const).map((isHalf) => (
              <button
                key={String(isHalf)}
                onClick={() => setHalf(isHalf)}
                className={`px-2.5 py-1 text-xs font-medium rounded transition-colors ${
                  half === isHalf
                    ? "bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-50 shadow-sm"
                    : "text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-50"
                }`}
              >
                {isHalf ? "My ½" : "Full"}
              </button>
            ))}
          </div>
        </div>
      </div>

      {rows.length < 2 ? (
        <div className="h-64 flex items-center justify-center text-sm text-gray-500 dark:text-gray-400 text-center px-4">
          Not enough data yet — chart builds up as monthly snapshots accumulate.
        </div>
      ) : (
        <div className="h-64 sm:h-80 -ml-2">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={rows} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={gradientColor} stopOpacity={0.2} />
                  <stop offset="100%" stopColor={gradientColor} stopOpacity={0} />
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
                width={72}
                domain={domain}
              />
              <Tooltip
                content={(props) => (
                  <CustomTooltip
                    active={props.active}
                    payload={props.payload as readonly TooltipPayloadItem[] | undefined}
                    label={props.label as string | undefined}
                    mode={mode}
                  />
                )}
                cursor={{ stroke: "#94a3b8", strokeDasharray: "3 3" }}
              />
              <Area
                type="monotone"
                dataKey="value"
                name={isBalance ? "Balance" : "Equity"}
                stroke={stroke}
                strokeWidth={2.25}
                fill={`url(#${gradientId})`}
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
