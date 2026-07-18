"use client";

import { useEffect, useRef, useState } from "react";
import {
  Bar, BarChart, CartesianGrid, LabelList, Rectangle,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { type SpendingRow } from "@/lib/queries";
import { CATEGORY_EMOJIS, getCategoryColor } from "@/lib/category-emojis";
import NavBtn from "./nav-btn";

type Props = { byCategory: SpendingRow[] };

type PieTooltip = {
  cat: string;
  value: number;
  pct: number;
  x: number;
  y: number;
};

const gbp = new Intl.NumberFormat("en-GB", {
  style: "currency",
  currency: "GBP",
  maximumFractionDigits: 0,
});

function monthLabel(m: string) {
  const [year, mon] = m.split("-");
  const d = new Date(Number(year), Number(mon) - 1, 1);
  return d.toLocaleDateString("en-GB", { month: "short", year: "2-digit" });
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function fmtBarLabel(v: any): string {
  const n = Number(v);
  if (!n) return "";
  if (n >= 1000) return `£${(n / 1000).toFixed(1)}k`;
  return `£${Math.round(n)}`;
}

function donutArc(
  cx: number, cy: number,
  outerR: number, innerR: number,
  startA: number, endA: number,
): string {
  const ox1 = cx + outerR * Math.cos(startA), oy1 = cy + outerR * Math.sin(startA);
  const ox2 = cx + outerR * Math.cos(endA),   oy2 = cy + outerR * Math.sin(endA);
  const ix1 = cx + innerR * Math.cos(endA),   iy1 = cy + innerR * Math.sin(endA);
  const ix2 = cx + innerR * Math.cos(startA), iy2 = cy + innerR * Math.sin(startA);
  const large = endA - startA > Math.PI ? 1 : 0;
  return (
    `M ${ox1} ${oy1} A ${outerR} ${outerR} 0 ${large} 1 ${ox2} ${oy2} ` +
    `L ${ix1} ${iy1} A ${innerR} ${innerR} 0 ${large} 0 ${ix2} ${iy2} Z`
  );
}

const tickFmt = (v: number) => {
  if (v === 0) return "£0";
  if (v >= 1000) return `£${(v / 1000).toFixed(0)}k`;
  return `£${v}`;
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function BarTip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  const items = [...payload].reverse().filter((p: any) => (p.value as number) > 0);
  const total = payload.reduce((s: number, p: any) => s + (p.value as number), 0);
  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-lg p-3 text-xs">
      <div className="font-semibold mb-1.5 text-gray-800 dark:text-gray-200">{label}</div>
      {/* The swatch is the only thing tying each row to its segment in the
          stack — unlike the legend below, which carries its own colour bars. */}
      {items.map((p: any) => (
        <div key={p.name} className="flex items-center justify-between gap-3 text-gray-600 dark:text-gray-400">
          <span className="flex items-center gap-1.5">
            <span
              className="w-2.5 h-2.5 rounded-sm shrink-0"
              style={{ backgroundColor: getCategoryColor(p.name) }}
            />
            {CATEGORY_EMOJIS[p.name] ?? "📦"} {p.name}
          </span>
          <span className="font-medium text-gray-800 dark:text-gray-200">{gbp.format(p.value)}</span>
        </div>
      ))}
      <div className="mt-1.5 pt-1.5 border-t border-gray-100 dark:border-gray-800 flex justify-between font-semibold text-gray-800 dark:text-gray-200">
        <span>Total</span>
        <span>{gbp.format(Math.round(total))}</span>
      </div>
    </div>
  );
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function DrillTip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-lg p-3 text-xs">
      <div className="font-semibold mb-1 text-gray-800 dark:text-gray-200">{label}</div>
      <span className="font-medium text-gray-800 dark:text-gray-200">{gbp.format(payload[0].value)}</span>
    </div>
  );
}

export default function CategoryChart({ byCategory }: Props) {
  const [chartType, setChartType]       = useState<"bars" | "pie">("bars");
  const [excludedCats, setExcludedCats] = useState<Set<string>>(new Set());
  const [barPage, setBarPage]           = useState(-1); // -1 = last page
  const [drillCat, setDrillCat]         = useState<string | null>(null);
  const [drillYearIdx, setDrillYearIdx] = useState(-1);
  const [pieMonthIdx, setPieMonthIdx]   = useState(-1);
  const [pieTooltip, setPieTooltip]     = useState<PieTooltip | null>(null);

  // Measure container width for the pie SVG (so it never uses viewBox scaling)
  const pieContainerRef = useRef<HTMLDivElement>(null);
  const [containerW, setContainerW] = useState(320);
  useEffect(() => {
    const el = pieContainerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(entries => {
      const w = entries[0]?.contentRect.width;
      if (w) setContainerW(Math.round(w));
    });
    ro.observe(el);
    setContainerW(el.clientWidth || 320);
    return () => ro.disconnect();
  }, []);

  // ── Base data ───────────────────────────────────────────────────────────────
  const monthSet = new Set<string>();
  const catTotals: Record<string, number> = {};
  for (const row of byCategory) {
    monthSet.add(row.month);
    catTotals[row.category] = (catTotals[row.category] ?? 0) + row.total;
  }

  const months = [...monthSet].sort();
  const rowByMonthCat = new Map(byCategory.map(r => [`${r.month}|${r.category}`, r.total]));

  // ── Bar chart: 6-month page pagination ────────────────────────────────────
  const BAR_PAGE_SIZE  = 6;
  const totalBarPages  = Math.max(1, Math.ceil(months.length / BAR_PAGE_SIZE));
  const actualBarPage  = barPage === -1 ? totalBarPages - 1 : Math.min(barPage, totalBarPages - 1);
  const pagedMonths    = months.slice(actualBarPage * BAR_PAGE_SIZE, (actualBarPage + 1) * BAR_PAGE_SIZE);
  const barPageLabel   = pagedMonths.length > 0
    ? `${monthLabel(pagedMonths[0])}${pagedMonths.length > 1 ? ` – ${monthLabel(pagedMonths[pagedMonths.length - 1])}` : ""}`
    : "";

  // ── Pie month selection ────────────────────────────────────────────────────
  const actualPieMonthIdx = pieMonthIdx === -1 ? months.length - 1 : Math.min(pieMonthIdx, months.length - 1);
  const selectedPieMonth  = months[actualPieMonthIdx] ?? "";

  // ── Categories in view ─────────────────────────────────────────────────────
  // Every category with spend in the period currently on screen — the selected
  // month in pie mode, the paginated 6-month window in bars mode — ranked by
  // that period's total. Categories with nothing spent in the period are
  // dropped. There is no top-N cap or "Other" bucket: a month runs to ~13
  // categories, which the stack and the list both show comfortably, and
  // capping buried real spend (Car, Entertainment) in an opaque roll-up.
  const periodMonths = chartType === "pie"
    ? (selectedPieMonth ? [selectedPieMonth] : [])
    : pagedMonths;

  const periodTotals: Record<string, number> = {};
  for (const cat of Object.keys(catTotals)) {
    const total = periodMonths.reduce((s, m) => s + (rowByMonthCat.get(`${m}|${cat}`) ?? 0), 0);
    if (total > 0) periodTotals[cat] = total;
  }

  const allVisible    = Object.entries(periodTotals).sort((a, b) => b[1] - a[1]).map(([c]) => c);
  const effectiveCats = allVisible.filter(c => !excludedCats.has(c));

  // Legend totals track the same period, so paginating changes the numbers below.
  const legendTotals: Record<string, number> = periodTotals;

  // ── Drill-down: year-based pagination ─────────────────────────────────────
  const monthsByYear: Record<string, string[]> = {};
  for (const m of months) {
    const yr = m.slice(0, 4);
    if (!monthsByYear[yr]) monthsByYear[yr] = [];
    monthsByYear[yr].push(m);
  }
  const years = Object.keys(monthsByYear).sort();

  const actualDrillYearIdx = drillYearIdx === -1 ? years.length - 1 : Math.min(drillYearIdx, years.length - 1);
  const drillYear          = years[actualDrillYearIdx] ?? "";
  const pagedDrillMonths   = monthsByYear[drillYear] ?? [];

  // ── Stacked bar data (for Recharts) ───────────────────────────────────────
  // Note: bars are kept mounted in a fixed order (allVisible) with excluded
  // categories zeroed out, rather than removed — Recharts doesn't reliably
  // preserve stack order when a Bar is unmounted then remounted later.
  function monthStackTotal(m: string): number {
    let total = 0;
    for (const cat of effectiveCats) {
      total += rowByMonthCat.get(`${m}|${cat}`) ?? 0;
    }
    return total;
  }

  // Which segment sits at the very top of each month's stack. This varies month
  // to month, so the stack total can't be pinned to one fixed Bar: the last
  // category in `allVisible` is the period's smallest, which is £0 in most
  // individual months — Recharts draws nothing for a zero-value segment, and
  // the total label disappears along with it. Resolve the topmost segment that
  // actually has a value, per month, and let that one carry the label.
  const topCatByMonth = pagedMonths.map(m => {
    for (let i = allVisible.length - 1; i >= 0; i--) {
      const cat = allVisible[i];
      if (excludedCats.has(cat)) continue;
      if ((rowByMonthCat.get(`${m}|${cat}`) ?? 0) > 0) return cat;
    }
    return null;
  });

  const stackBarData = pagedMonths.map((m, i) => {
    const row: Record<string, string | number | null> = { label: monthLabel(m) };
    for (const cat of allVisible) {
      const val = excludedCats.has(cat) ? 0 : (rowByMonthCat.get(`${m}|${cat}`) ?? 0);
      row[cat] = Math.round(val * 100) / 100;
    }
    row.__total   = Math.round(monthStackTotal(m));
    row.__topCat  = topCatByMonth[i];
    return row;
  });
  // Fixed across all pages so stacked-bar heights stay comparable while paginating.
  const globalStackMax = Math.max(0, ...months.map(monthStackTotal));

  // ── Drill-down bar data (for Recharts) ────────────────────────────────────
  function monthDrillValue(m: string): number {
    return rowByMonthCat.get(`${m}|${drillCat ?? ""}`) ?? 0;
  }

  const drillAllTotal = months.reduce((s, m) => s + monthDrillValue(m), 0);
  const drillAvg = months.length > 0 ? drillAllTotal / months.length : 0;

  const drillBarData = pagedDrillMonths.map(m => ({
    label: monthLabel(m),
    val: Math.round(monthDrillValue(m) * 100) / 100,
  }));
  // Fixed across all years so drill-down bar heights stay comparable while paginating.
  const globalDrillMax = Math.max(0, ...months.map(monthDrillValue));

  // ── Pie/donut data ─────────────────────────────────────────────────────────
  // In pie mode the period is the selected month, so legendTotals already holds
  // exactly the per-slice values.
  const pieTotals: Record<string, number> = {};
  for (const cat of effectiveCats) pieTotals[cat] = legendTotals[cat] ?? 0;
  const pieGrand = Object.values(pieTotals).reduce((s, v) => s + v, 0);
  let cumA = -Math.PI / 2;
  const pieSlices = effectiveCats
    .map(cat => {
      const val   = pieTotals[cat] ?? 0;
      const angle = pieGrand > 0 ? (val / pieGrand) * Math.PI * 2 : 0;
      const start = cumA;
      cumA += angle;
      return { cat, val, pct: pieGrand > 0 ? (val / pieGrand) * 100 : 0, startA: start, endA: cumA };
    })
    .filter(s => s.val > 0 && s.endA - s.startA > 0.01);

  // Pie dimensions — computed from actual container width, no viewBox scaling
  const OUTER_R = Math.min(150, Math.floor((containerW - 20) / 2));
  const INNER_R = Math.round(OUTER_R * 0.55);
  const PIE_H   = OUTER_R * 2 + 20;
  const PIE_CX  = containerW / 2;
  const PIE_CY  = PIE_H / 2;

  // ── Helpers ────────────────────────────────────────────────────────────────
  function toggleExclude(cat: string) {
    setExcludedCats(prev => {
      const next = new Set(prev);
      next.has(cat) ? next.delete(cat) : next.add(cat);
      return next;
    });
  }

  // Drawn from all-time categories, not the current period, so the checkboxes
  // don't appear/disappear as you paginate.
  const exclusionOffers = ["Mortgage", "Home", "Bills"].filter(c => c in catTotals);
  const legendGrand     = effectiveCats.reduce((s, c) => s + (legendTotals[c] ?? 0), 0);
  const drillColor      = drillCat ? getCategoryColor(drillCat) : "#3b82f6";

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4 sm:p-6 shadow-sm">

      {/* Header */}
      {drillCat ? (
        <div className="mb-3">
          <button
            onClick={() => setDrillCat(null)}
            className="text-xs text-gray-500 dark:text-gray-400 hover:underline mb-1"
          >
            ← Overview
          </button>
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">
              {CATEGORY_EMOJIS[drillCat] ?? "📦"} {drillCat}
            </h2>
            <span className="text-xs text-gray-400 tabular-nums shrink-0">
              avg {gbp.format(Math.round(drillAvg))}/mo
            </span>
          </div>
        </div>
      ) : (
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">
            Spending by Category
          </h2>
          <div className="flex items-center gap-0.5 bg-gray-100 dark:bg-gray-800 rounded-md p-0.5">
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
      )}

      {/* Chart area */}
      <div className="relative" ref={pieContainerRef}>
        {drillCat ? (
          /* Single-category drill-down — Recharts bar */
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={drillBarData} margin={{ top: 20, right: 4, left: 0, bottom: 4 }} barCategoryGap="20%">
              <CartesianGrid strokeDasharray="3 3" className="stroke-gray-100 dark:stroke-gray-800" vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 11, fill: "currentColor" }} tickLine={false} axisLine={false} />
              <YAxis
                tick={{ fontSize: 11, fill: "currentColor" }}
                tickLine={false}
                axisLine={false}
                tickFormatter={tickFmt}
                width={42}
                domain={[0, (dataMax: number) => Math.max(dataMax, globalDrillMax)]}
              />
              <Tooltip content={<DrillTip />} />
              <Bar dataKey="val" fill={drillColor} radius={[3, 3, 0, 0]}>
                <LabelList dataKey="val" position="top" formatter={fmtBarLabel} style={{ fontSize: 11, fill: "currentColor", opacity: 0.55 }} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>

        ) : chartType === "bars" ? (
          /* Stacked bar chart — Recharts */
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={stackBarData} margin={{ top: 20, right: 4, left: 0, bottom: 4 }} barCategoryGap="20%">
              <CartesianGrid strokeDasharray="3 3" className="stroke-gray-100 dark:stroke-gray-800" vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 11, fill: "currentColor" }} tickLine={false} axisLine={false} />
              <YAxis
                tick={{ fontSize: 11, fill: "currentColor" }}
                tickLine={false}
                axisLine={false}
                tickFormatter={tickFmt}
                width={42}
                domain={[0, (dataMax: number) => Math.max(dataMax, globalStackMax)]}
              />
              <Tooltip content={<BarTip />} />
              {allVisible.map(cat => (
                <Bar
                  key={cat}
                  dataKey={cat}
                  stackId="a"
                  fill={getCategoryColor(cat)}
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                  shape={(p: any) => (
                    <Rectangle {...p} radius={p.payload?.__topCat === cat ? [3, 3, 0, 0] : 0} />
                  )}
                >
                  <LabelList
                    dataKey="__total"
                    // eslint-disable-next-line @typescript-eslint/no-explicit-any
                    content={(p: any) =>
                      topCatByMonth[p.index] === cat && p.value ? (
                        <text
                          x={p.x + p.width / 2}
                          y={p.y - 6}
                          textAnchor="middle"
                          style={{ fontSize: 11, fill: "currentColor", opacity: 0.55 }}
                        >
                          {fmtBarLabel(p.value)}
                        </text>
                      ) : null
                    }
                  />
                </Bar>
              ))}
            </BarChart>
          </ResponsiveContainer>

        ) : (
          /* Donut chart — custom SVG with explicit width (no viewBox scaling) */
          <svg
            width={containerW}
            height={PIE_H}
            onMouseLeave={() => setPieTooltip(null)}
          >
            {pieSlices.map(slice => (
              <path
                key={slice.cat}
                d={donutArc(PIE_CX, PIE_CY, OUTER_R, INNER_R, slice.startA, slice.endA)}
                fill={getCategoryColor(slice.cat)}
                stroke="white"
                strokeWidth={1.5}
                className="cursor-pointer"
                onMouseEnter={e => {
                  const svg = (e.target as SVGElement).closest("svg")!;
                  const rect = svg.getBoundingClientRect();
                  setPieTooltip({
                    cat: slice.cat,
                    value: slice.val,
                    pct: slice.pct,
                    x: e.clientX - rect.left,
                    y: e.clientY - rect.top,
                  });
                }}
              />
            ))}
            <text
              x={PIE_CX} y={PIE_CY - 12}
              textAnchor="middle" fontSize={13} fill="currentColor" opacity={0.45}
            >
              {selectedPieMonth ? monthLabel(selectedPieMonth) : "Total"}
            </text>
            <text
              x={PIE_CX} y={PIE_CY + 14}
              textAnchor="middle" fontSize={20} fontWeight={600} fill="currentColor"
            >
              {pieGrand >= 1000 ? `£${(pieGrand / 1000).toFixed(1)}k` : `£${Math.round(pieGrand)}`}
            </text>
          </svg>
        )}

        {/* Pie hover tooltip */}
        {pieTooltip && (
          <div
            className="pointer-events-none absolute z-10 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-lg p-3 text-xs"
            style={{
              left: `${(pieTooltip.x / containerW) * 100}%`,
              top:  `${(pieTooltip.y / PIE_H) * 100}%`,
              transform: "translate(-50%, -115%)",
              minWidth: 140,
            }}
          >
            <div className="font-semibold mb-1 text-gray-800 dark:text-gray-200">
              {CATEGORY_EMOJIS[pieTooltip.cat] ?? "📦"} {pieTooltip.cat}
            </div>
            <div className="flex justify-between gap-3 text-gray-600 dark:text-gray-400">
              <span>Total</span>
              <span className="font-medium text-gray-800 dark:text-gray-200">
                {gbp.format(pieTooltip.value)}
              </span>
            </div>
            <div className="flex justify-between gap-3 text-gray-600 dark:text-gray-400">
              <span>Share</span>
              <span className="font-medium text-gray-800 dark:text-gray-200">
                {pieTooltip.pct.toFixed(1)}%
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Bars: 6-month page navigation */}
      {!drillCat && chartType === "bars" && totalBarPages > 1 && (
        <div className="flex items-center justify-between mt-3">
          <NavBtn direction="left" onClick={() => setBarPage(Math.max(0, actualBarPage - 1))} disabled={actualBarPage === 0} />
          <span className="text-xs font-medium text-gray-500 tabular-nums">{barPageLabel}</span>
          <NavBtn direction="right" onClick={() => setBarPage(Math.min(totalBarPages - 1, actualBarPage + 1))} disabled={actualBarPage === totalBarPages - 1} />
        </div>
      )}

      {/* Drill-down: year navigation */}
      {!!drillCat && years.length > 1 && (
        <div className="flex items-center justify-between mt-3">
          <NavBtn direction="left" onClick={() => setDrillYearIdx(Math.max(0, actualDrillYearIdx - 1))} disabled={actualDrillYearIdx === 0} />
          <span className="text-xs font-medium text-gray-500 tabular-nums">{drillYear}</span>
          <NavBtn direction="right" onClick={() => setDrillYearIdx(Math.min(years.length - 1, actualDrillYearIdx + 1))} disabled={actualDrillYearIdx === years.length - 1} />
        </div>
      )}

      {/* Pie month navigation */}
      {chartType === "pie" && !drillCat && months.length > 1 && (
        <div className="flex items-center justify-between mt-3">
          <NavBtn
            direction="left"
            onClick={() => setPieMonthIdx(Math.max(0, actualPieMonthIdx - 1))}
            disabled={actualPieMonthIdx === 0}
          />
          <span className="text-xs font-medium text-gray-500 tabular-nums">
            {monthLabel(selectedPieMonth)}
          </span>
          <NavBtn
            direction="right"
            onClick={() => setPieMonthIdx(Math.min(months.length - 1, actualPieMonthIdx + 1))}
            disabled={actualPieMonthIdx === months.length - 1}
          />
        </div>
      )}

      {/* Exclusion checkboxes */}
      {!drillCat && exclusionOffers.length > 0 && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-3 pt-3 border-t border-gray-100 dark:border-gray-800 text-xs text-gray-500 dark:text-gray-400">
          <span className="font-medium text-gray-600 dark:text-gray-400">Exclude:</span>
          {exclusionOffers.map(cat => (
            <label
              key={cat}
              className="flex items-center gap-1.5 cursor-pointer hover:text-gray-700 dark:hover:text-gray-300 select-none"
            >
              <input
                type="checkbox"
                checked={excludedCats.has(cat)}
                onChange={() => toggleExclude(cat)}
                className="w-3.5 h-3.5 rounded accent-blue-500"
              />
              {CATEGORY_EMOJIS[cat] ?? "📦"} {cat}
            </label>
          ))}
        </div>
      )}

      {/* Category legend — vertical list with drill-down */}
      {!drillCat && (
        <div className="mt-3 space-y-0.5">
          {effectiveCats.map(cat => {
            const total = legendTotals[cat] ?? 0;
            const pct   = legendGrand > 0 ? total / legendGrand : 0;
            return (
              <button
                key={cat}
                className="w-full flex items-center gap-2 py-1.5 px-2 rounded-lg text-left hover:bg-gray-50 dark:hover:bg-gray-900 transition-colors group"
                onClick={() => { setDrillCat(cat); setDrillYearIdx(-1); }}
              >
                <span className="text-xs text-gray-700 dark:text-gray-300 w-28 shrink-0 truncate">
                  {CATEGORY_EMOJIS[cat] ?? "📦"} {cat}
                </span>
                <div className="flex-1 h-1.5 rounded-full bg-gray-100 dark:bg-gray-800 overflow-hidden">
                  <div
                    className="h-full rounded-full"
                    style={{ width: `${pct * 100}%`, backgroundColor: getCategoryColor(cat) }}
                  />
                </div>
                <span className="text-xs tabular-nums text-gray-500 dark:text-gray-400 w-16 text-right shrink-0">
                  {gbp.format(total)}
                </span>
                <span className="text-gray-300 dark:text-gray-600 group-hover:text-gray-400 shrink-0 text-xs">
                  ›
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
