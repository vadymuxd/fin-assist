"use client";

import { useMemo } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { PricePoint } from "@/lib/queries";

type Row = { date: string; pct: number };

function shortDate(iso: string) {
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    timeZone: "UTC",
  });
}

type TooltipEntry = {
  dataKey?: string | number;
  value?: number | string | (number | string)[];
  color?: string;
};

function CustomTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: readonly TooltipEntry[];
  label?: string | number;
}) {
  if (!active || !payload || payload.length === 0) return null;
  const v = typeof payload[0].value === "number" ? payload[0].value : Number(Array.isArray(payload[0].value) ? payload[0].value[0] : (payload[0].value ?? 0));
  const sign = v >= 0 ? "+" : "";
  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white/95 dark:bg-gray-900/95 backdrop-blur p-2.5 shadow-lg text-xs">
      <div className="font-medium text-gray-500 dark:text-gray-400 mb-0.5">
        {typeof label === "string" ? shortDate(label) : ""}
      </div>
      <div className={`font-semibold tabular-nums ${v >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-rose-500 dark:text-rose-400"}`}>
        {sign}{v.toFixed(2)}%
      </div>
    </div>
  );
}

export default function HoldingPriceChart({
  history,
  avgBuy,
  ticker,
}: {
  history: PricePoint[];
  avgBuy: number | null;
  ticker: string;
}) {
  const rows: Row[] = useMemo(() => {
    if (!avgBuy || avgBuy <= 0 || history.length === 0) return [];
    return history.map((p) => ({
      date: p.date,
      pct: ((p.price - avgBuy) / avgBuy) * 100,
    }));
  }, [history, avgBuy]);

  if (rows.length < 2) {
    return (
      <div className="h-48 flex items-center justify-center text-sm text-gray-400 dark:text-gray-500">
        No price history yet.
      </div>
    );
  }

  const values = rows.map((r) => r.pct);
  const minV = Math.min(...values);
  const maxV = Math.max(...values);
  const padding = Math.max((maxV - minV) * 0.15, 2);
  const domain: [number, number] = [minV - padding, maxV + padding];

  const currentPct = rows[rows.length - 1].pct;
  const isUp = currentPct >= 0;
  const lineColor = isUp ? "#10b981" : "#f43f5e";

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs text-gray-500 dark:text-gray-400">
          % return vs avg buy · {shortDate(rows[0].date)} – {shortDate(rows[rows.length - 1].date)}
        </p>
        <span className={`text-sm font-semibold tabular-nums ${isUp ? "text-emerald-600 dark:text-emerald-400" : "text-rose-500 dark:text-rose-400"}`}>
          {isUp ? "+" : ""}{currentPct.toFixed(2)}%
        </span>
      </div>
      <div className="h-48 -ml-2">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id={`fill-${ticker}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={lineColor} stopOpacity={0.2} />
                <stop offset="100%" stopColor={lineColor} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" className="stroke-gray-100 dark:stroke-gray-800" vertical={false} />
            <XAxis
              dataKey="date"
              tickFormatter={shortDate}
              tick={{ fontSize: 10, fill: "currentColor" }}
              className="text-gray-400 dark:text-gray-500"
              tickLine={false}
              axisLine={false}
              minTickGap={48}
            />
            <YAxis
              tick={{ fontSize: 10, fill: "currentColor" }}
              className="text-gray-400 dark:text-gray-500"
              tickLine={false}
              axisLine={false}
              tickFormatter={(v) => `${v >= 0 ? "+" : ""}${v.toFixed(0)}%`}
              width={52}
              domain={domain}
            />
            <Tooltip
              content={(props) => (
                <CustomTooltip
                  active={props.active}
                  payload={props.payload as readonly TooltipEntry[] | undefined}
                  label={props.label}
                />
              )}
              cursor={{ stroke: "#94a3b8", strokeDasharray: "3 3" }}
            />
            <ReferenceLine y={0} stroke="#94a3b8" strokeDasharray="4 4" strokeWidth={1} />
            <Area
              type="monotone"
              dataKey="pct"
              stroke={lineColor}
              strokeWidth={2}
              fill={`url(#fill-${ticker})`}
              dot={false}
              activeDot={{ r: 3, fill: lineColor }}
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
