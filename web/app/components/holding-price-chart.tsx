"use client";

import { useMemo } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { HoldingTrade, PricePoint } from "@/lib/queries";

const START_ISO = "2026-04-13";
const UP = "#10b981"; // emerald-500 — above the 0% baseline
const DOWN = "#f43f5e"; // rose-500 — below the 0% baseline

type Row = { date: string; pct: number };

function shortDate(iso: string) {
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    timeZone: "UTC",
  });
}

function pctStr(v: number) {
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
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
  const v =
    typeof payload[0].value === "number"
      ? payload[0].value
      : Number(
          Array.isArray(payload[0].value)
            ? payload[0].value[0]
            : (payload[0].value ?? 0),
        );
  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white/95 dark:bg-gray-900/95 backdrop-blur p-2.5 shadow-lg text-xs">
      <div className="font-medium text-gray-500 dark:text-gray-400 mb-0.5">
        {typeof label === "string" ? shortDate(label) : ""}
      </div>
      <div
        className={`font-semibold tabular-nums ${v >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-rose-500 dark:text-rose-400"}`}
      >
        Ticker {pctStr(v)}
      </div>
    </div>
  );
}

type DotProps = { cx?: number; cy?: number; payload?: Row };

function renderActiveDot({ cx, cy, payload }: DotProps) {
  if (cx == null || cy == null) return <g />;
  const c = (payload?.pct ?? 0) >= 0 ? UP : DOWN;
  return <circle cx={cx} cy={cy} r={3.5} fill={c} stroke="#fff" strokeWidth={1.5} />;
}

/**
 * Build the chart line: the RAW ticker price return since Apr 13, indexed to 0%
 * on the first trading day on/after the tracking start. This is the ticker's own
 * performance — independent of when (or whether) the user actually bought it.
 *
 * It is deliberately different from the header number: the header shows the
 * user's REAL money-weighted return (Sheet col K), which depends on actual
 * purchase timing. Comparing the two shows how the ticker moved vs. what the
 * user earned by entering later.
 */
function buildLineRows(history: PricePoint[]): { rows: Row[]; tickerPct: number | null } {
  const filtered = history.filter((p) => p.date >= START_ISO);
  if (filtered.length < 2) return { rows: [], tickerPct: null };

  const base = filtered[0].price;
  if (!base || base <= 0) return { rows: [], tickerPct: null };

  const rows: Row[] = filtered.map((p) => ({
    date: p.date,
    pct: (p.price / base - 1) * 100,
  }));
  return { rows, tickerPct: rows[rows.length - 1].pct };
}

/**
 * Map each post-Apr-13 buy to the nearest chart date so its marker always
 * renders. Recharts only draws a ReferenceLine when x exactly matches a data
 * point, but a buy can land on a weekend or a day missing from price history
 * (e.g. stale backfill), so snap to the last chart date on/before the buy.
 */
function buyMarkerDates(trades: HoldingTrade[], rows: Row[]): string[] {
  if (rows.length === 0) return [];
  const rowDates = rows.map((r) => r.date); // ascending
  const snapped = new Set<string>();
  for (const t of trades) {
    if (t.action !== "BUY" || t.date < START_ISO) continue;
    let pick: string | null = null;
    for (const d of rowDates) {
      if (d <= t.date) pick = d; // keep the latest date on/before the buy
    }
    snapped.add(pick ?? rowDates[0]); // buy precedes all data → snap to first
  }
  return [...snapped].sort();
}

export default function HoldingPriceChart({
  history,
  trades,
  ticker,
  trackingPct,
}: {
  history: PricePoint[];
  trades: HoldingTrade[];
  ticker: string;
  /** Real return since Apr 13 (Sheet col K). Falls back to the ticker line if null. */
  trackingPct: number | null;
}) {
  const { rows, tickerPct } = useMemo(() => buildLineRows(history), [history]);
  const buyDates = useMemo(() => buyMarkerDates(trades, rows), [trades, rows]);

  if (rows.length < 2) {
    return (
      <div className="h-48 flex items-center justify-center text-sm text-gray-400 dark:text-gray-500">
        No price history since 13 Apr.
      </div>
    );
  }

  const values = rows.map((r) => r.pct);
  const minV = Math.min(...values, 0);
  const maxV = Math.max(...values, 0);
  const padding = Math.max((maxV - minV) * 0.15, 2);
  const domainMin = minV - padding;
  const domainMax = maxV + padding;
  const domain: [number, number] = [domainMin, domainMax];

  // Fraction from the top of the path bounding box where 0% sits.
  // Must use maxV/minV (actual data extremes), NOT the padded domain — the SVG
  // gradient uses objectBoundingBox which maps to the path extent, not the axis.
  const off = maxV <= 0 ? 0 : minV >= 0 ? 1 : maxV / (maxV - minV);

  const realPct = trackingPct ?? tickerPct ?? 0;
  const realUp = realPct >= 0;

  return (
    <div>
      <div className="flex items-end justify-between gap-3 mb-3">
        {/* Left: the headline — the user's real return */}
        <div>
          <div
            className={`text-2xl font-semibold tabular-nums ${realUp ? "text-emerald-600 dark:text-emerald-400" : "text-rose-500 dark:text-rose-400"}`}
          >
            {pctStr(realPct)}
          </div>
          <div className="text-xs text-gray-500 dark:text-gray-400">
            Your real return since 13 Apr
          </div>
        </div>
        {/* Right: the ticker line total, for comparison */}
        {tickerPct !== null && (
          <div className="text-right">
            <div className="text-sm font-medium tabular-nums text-gray-900 dark:text-gray-50">
              {pctStr(tickerPct)}
            </div>
            <div className="text-xs text-gray-500 dark:text-gray-400">
              Ticker price since 13 Apr
            </div>
          </div>
        )}
      </div>
      <div className="h-48 -ml-2">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id={`stroke-${ticker}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset={off} stopColor={UP} />
                <stop offset={off} stopColor={DOWN} />
              </linearGradient>
              <linearGradient id={`area-${ticker}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset={0} stopColor={UP} stopOpacity={0.22} />
                <stop offset={off} stopColor={UP} stopOpacity={0.02} />
                <stop offset={off} stopColor={DOWN} stopOpacity={0.02} />
                <stop offset={1} stopColor={DOWN} stopOpacity={0.22} />
              </linearGradient>
            </defs>
            <CartesianGrid
              strokeDasharray="3 3"
              className="stroke-gray-100 dark:stroke-gray-800"
              vertical={false}
            />
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
            {buyDates.map((d) => {
              // Flip the label inward when the marker sits near the right edge,
              // otherwise "Buy" gets clipped off the chart.
              const idx = rows.findIndex((r) => r.date >= d);
              const nearRight = idx === -1 || idx > (rows.length - 1) * 0.85;
              return (
                <ReferenceLine
                  key={d}
                  x={d}
                  stroke="#f59e0b"
                  strokeDasharray="3 3"
                  strokeWidth={1.5}
                  label={{
                    value: "Buy",
                    position: nearRight ? "insideTopRight" : "insideTopLeft",
                    fontSize: 9,
                    fill: "#f59e0b",
                  }}
                />
              );
            })}
            <Area
              type="monotone"
              dataKey="pct"
              stroke={`url(#stroke-${ticker})`}
              strokeWidth={2}
              fill={`url(#area-${ticker})`}
              baseValue={0}
              dot={false}
              activeDot={renderActiveDot}
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
