"use client";

import { useState } from "react";
import { type SpendingRow } from "@/lib/queries";
import { CATEGORY_EMOJIS, getCategoryColor } from "@/lib/category-emojis";
import NavBtn from "./nav-btn";

type Props = { byCategory: SpendingRow[] };

type BarTooltip = {
  x: number;
  month: string;
  items: { cat: string; value: number }[];
};

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

// SVG layout constants
const W = 620, H = 240;
const PAD_L = 44, PAD_R = 8, PAD_T = 8, PAD_B = 24;
const plotW = W - PAD_L - PAD_R;
const plotH = H - PAD_T - PAD_B;
const BAR_GAP = 0.2;

function scaleY(v: number, domainMax: number) {
  return PAD_T + plotH - (v / domainMax) * plotH;
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

function fmtBarLabel(v: number): string {
  if (v <= 0) return "";
  if (v >= 1000) return `£${(v / 1000).toFixed(1)}k`;
  return `£${Math.round(v)}`;
}

function fmtTick(tick: number, domainMax: number): string {
  if (tick === 0) return "£0";
  if (domainMax >= 2000) return `£${Math.round(tick / 1000)}k`;
  if (domainMax >= 1000) return `£${(tick / 1000).toFixed(1)}k`;
  return `£${Math.round(tick)}`;
}

function GridAndTicks({ domainMax }: { domainMax: number }) {
  // Step-aligned ticks so labels never duplicate
  const step = domainMax >= 5000 ? 2000
    : domainMax >= 2000 ? 1000
    : domainMax >= 1000 ? 500
    : domainMax >= 400  ? 200
    : 100;
  const ticks = Array.from(
    { length: Math.floor(domainMax / step) + 1 },
    (_, i) => i * step,
  );
  return (
    <>
      {ticks.map(tick => {
        const y = scaleY(tick, domainMax);
        return (
          <g key={tick}>
            <line
              x1={PAD_L} x2={W - PAD_R} y1={y} y2={y}
              stroke="currentColor" strokeOpacity={0.08} strokeWidth={1}
            />
            <text
              x={PAD_L - 4} y={y}
              textAnchor="end" dominantBaseline="middle"
              fontSize={9} fill="currentColor" opacity={0.5}
            >
              {fmtTick(tick, domainMax)}
            </text>
          </g>
        );
      })}
    </>
  );
}

export default function CategoryChart({ byCategory }: Props) {
  const [chartType, setChartType]         = useState<"bars" | "pie">("bars");
  const [excludedCats, setExcludedCats]   = useState<Set<string>>(new Set());
  const [yearIdx, setYearIdx]             = useState(-1); // -1 = most recent year
  const [drillCat, setDrillCat]           = useState<string | null>(null);
  const [drillYearIdx, setDrillYearIdx]   = useState(-1);
  const [pieMonthIdx, setPieMonthIdx]     = useState(-1); // -1 = most recent month
  const [barTooltip, setBarTooltip]       = useState<BarTooltip | null>(null);
  const [pieTooltip, setPieTooltip]       = useState<PieTooltip | null>(null);

  // ── Base data ───────────────────────────────────────────────────────────────
  const monthSet = new Set<string>();
  const catTotals: Record<string, number> = {};
  for (const row of byCategory) {
    monthSet.add(row.month);
    catTotals[row.category] = (catTotals[row.category] ?? 0) + row.total;
  }

  const allCats   = Object.entries(catTotals).sort((a, b) => b[1] - a[1]);
  const topCats   = allCats.slice(0, 9).map(([c]) => c);
  const hasOther  = allCats.length > 9;
  const allVisible = hasOther ? [...topCats, "Other"] : topCats;

  const effectiveCats = allVisible.filter(c => !excludedCats.has(c));

  const months = [...monthSet].sort();
  const rowByMonthCat = new Map(byCategory.map(r => [`${r.month}|${r.category}`, r.total]));

  // ── Pie month selection ────────────────────────────────────────────────────
  const actualPieMonthIdx = pieMonthIdx === -1 ? months.length - 1 : Math.min(pieMonthIdx, months.length - 1);
  const selectedPieMonth  = months[actualPieMonthIdx] ?? "";

  // Extended totals for legend/pie — per-month in pie mode, all-time otherwise
  const legendTotals: Record<string, number> = {};
  if (chartType === "pie" && selectedPieMonth) {
    for (const [cat] of allCats) {
      legendTotals[cat] = rowByMonthCat.get(`${selectedPieMonth}|${cat}`) ?? 0;
    }
    if (hasOther) {
      legendTotals["Other"] = allCats.slice(9).reduce((s, [c]) => s + (rowByMonthCat.get(`${selectedPieMonth}|${c}`) ?? 0), 0);
    }
  } else {
    Object.assign(legendTotals, catTotals);
    if (hasOther) {
      legendTotals["Other"] = allCats.slice(9).reduce((s, [, v]) => s + v, 0);
    }
  }

  // ── Year-based pagination ──────────────────────────────────────────────────
  const monthsByYear: Record<string, string[]> = {};
  for (const m of months) {
    const yr = m.slice(0, 4);
    if (!monthsByYear[yr]) monthsByYear[yr] = [];
    monthsByYear[yr].push(m);
  }
  const years = Object.keys(monthsByYear).sort();

  const actualYearIdx   = yearIdx === -1 ? years.length - 1 : Math.min(yearIdx, years.length - 1);
  const selectedYear    = years[actualYearIdx] ?? "";
  const pagedMonths     = monthsByYear[selectedYear] ?? [];

  const actualDrillYearIdx = drillYearIdx === -1 ? years.length - 1 : Math.min(drillYearIdx, years.length - 1);
  const drillYear          = years[actualDrillYearIdx] ?? "";
  const pagedDrillMonths   = monthsByYear[drillYear] ?? [];

  // ── Stacked bar month data ─────────────────────────────────────────────────
  const monthData = pagedMonths.map(m => {
    const rawVals: Record<string, number> = {};
    let other = 0;
    for (const [cat] of allCats) {
      const val = rowByMonthCat.get(`${m}|${cat}`) ?? 0;
      if (topCats.includes(cat)) rawVals[cat] = val;
      else other += val;
    }
    if (hasOther) rawVals["Other"] = Math.round(other * 100) / 100;
    const total = effectiveCats.reduce((s, c) => s + (rawVals[c] ?? 0), 0);
    return { month: m, label: monthLabel(m), rawVals, total };
  });

  const maxTotal  = Math.max(...monthData.map(d => d.total), 1);
  const domainMax = Math.ceil(maxTotal / 1000) * 1000;
  const barW  = (plotW / Math.max(pagedMonths.length, 1)) * (1 - BAR_GAP);
  const bandW = plotW / Math.max(pagedMonths.length, 1);

  // ── Pie/donut data ─────────────────────────────────────────────────────────
  const pieTotals: Record<string, number> = {};
  for (const cat of effectiveCats) {
    if (selectedPieMonth) {
      pieTotals[cat] = cat === "Other"
        ? allCats.slice(9).reduce((s, [c]) => s + (rowByMonthCat.get(`${selectedPieMonth}|${c}`) ?? 0), 0)
        : (rowByMonthCat.get(`${selectedPieMonth}|${cat}`) ?? 0);
    } else {
      pieTotals[cat] = cat === "Other"
        ? allCats.slice(9).reduce((s, [, v]) => s + v, 0)
        : (catTotals[cat] ?? 0);
    }
  }
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

  const PIE_H = 380;
  const PIE_CX = W / 2, PIE_CY = PIE_H / 2, OUTER_R = 155, INNER_R = 85;

  // ── Drill-down bar data ────────────────────────────────────────────────────
  const drillData = pagedDrillMonths.map(m => {
    const val = drillCat === "Other"
      ? allCats.slice(9).reduce((s, [cat]) => s + (rowByMonthCat.get(`${m}|${cat}`) ?? 0), 0)
      : (rowByMonthCat.get(`${m}|${drillCat ?? ""}`) ?? 0);
    return { month: m, label: monthLabel(m), val: Math.round(val * 100) / 100 };
  });

  const drillAllTotal = months.reduce((s, m) => {
    const val = drillCat === "Other"
      ? allCats.slice(9).reduce((ss, [cat]) => ss + (rowByMonthCat.get(`${m}|${cat}`) ?? 0), 0)
      : (rowByMonthCat.get(`${m}|${drillCat ?? ""}`) ?? 0);
    return s + val;
  }, 0);
  const drillAvg = months.length > 0 ? drillAllTotal / months.length : 0;

  const drillMax = Math.max(...drillData.map(d => d.val), 1);
  const drillStep = drillMax < 200 ? 50 : drillMax < 1000 ? 200 : drillMax < 5000 ? 500 : 1000;
  const drillDomain = Math.ceil(drillMax / drillStep) * drillStep || drillStep;
  const drillBarW   = (plotW / Math.max(pagedDrillMonths.length, 1)) * (1 - BAR_GAP);
  const drillBandW  = plotW / Math.max(pagedDrillMonths.length, 1);

  // ── Helpers ────────────────────────────────────────────────────────────────
  function toggleExclude(cat: string) {
    setExcludedCats(prev => {
      const next = new Set(prev);
      next.has(cat) ? next.delete(cat) : next.add(cat);
      return next;
    });
  }

  const exclusionOffers = allVisible.filter(c => ["Mortgage", "Home", "Bills"].includes(c));
  const legendGrand     = effectiveCats.reduce((s, c) => s + (legendTotals[c] ?? 0), 0);

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
      <div className="relative">
        {drillCat ? (
          /* Single-category drill-down */
          <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height: 240 }}>
            <GridAndTicks domainMax={drillDomain} />
            {drillData.map((d, mi) => {
              const x0   = PAD_L + mi * drillBandW + (drillBandW - drillBarW) / 2;
              const barH = (d.val / drillDomain) * plotH;
              const y    = PAD_T + plotH - barH;
              return (
                <g key={d.month}>
                  <rect
                    x={x0} y={y} width={drillBarW} height={barH}
                    fill={getCategoryColor(drillCat)} rx={2} ry={2}
                  />
                  {d.val > 0 && (
                    <text
                      x={x0 + drillBarW / 2} y={Math.max(PAD_T + 10, y - 3)}
                      textAnchor="middle" fontSize={9} fill="currentColor" opacity={0.55}
                    >
                      {fmtBarLabel(d.val)}
                    </text>
                  )}
                  <text
                    x={x0 + drillBarW / 2} y={H - 4}
                    textAnchor="middle" fontSize={11} fill="currentColor" opacity={0.5}
                  >
                    {d.label}
                  </text>
                </g>
              );
            })}
          </svg>

        ) : chartType === "bars" ? (
          /* Stacked bar chart */
          <svg
            viewBox={`0 0 ${W} ${H}`}
            className="w-full"
            style={{ height: 240 }}
            onMouseLeave={() => setBarTooltip(null)}
          >
            <GridAndTicks domainMax={domainMax} />
            {monthData.map((d, mi) => {
              const x0 = PAD_L + mi * bandW + (bandW - barW) / 2;
              let cumY = scaleY(0, domainMax);
              return (
                <g
                  key={d.month}
                  onMouseEnter={() =>
                    setBarTooltip({
                      x: x0 + barW / 2,
                      month: d.label,
                      items: effectiveCats
                        .map(c => ({ cat: c, value: d.rawVals[c] ?? 0 }))
                        .filter(i => i.value > 0),
                    })
                  }
                >
                  {effectiveCats.map((cat, ci) => {
                    const val = d.rawVals[cat] ?? 0;
                    if (val === 0) return null;
                    const barH = (val / domainMax) * plotH;
                    const y    = cumY - barH;
                    cumY = y;
                    const isTop = effectiveCats.slice(ci + 1).every(c => (d.rawVals[c] ?? 0) === 0);
                    return (
                      <rect
                        key={cat}
                        x={x0} y={y} width={barW} height={barH}
                        fill={getCategoryColor(cat)}
                        rx={isTop ? 2 : 0} ry={isTop ? 2 : 0}
                      />
                    );
                  })}
                  {d.total > 0 && (
                    <text
                      x={x0 + barW / 2}
                      y={Math.max(PAD_T + 10, scaleY(d.total, domainMax) - 3)}
                      textAnchor="middle" fontSize={9} fill="currentColor" opacity={0.55}
                    >
                      {fmtBarLabel(d.total)}
                    </text>
                  )}
                </g>
              );
            })}
            {pagedMonths.map((m, mi) => (
              <text
                key={m}
                x={PAD_L + mi * bandW + bandW / 2} y={H - 4}
                textAnchor="middle" fontSize={9} fill="currentColor" opacity={0.5}
              >
                {monthLabel(m)}
              </text>
            ))}
          </svg>

        ) : (
          /* Donut chart */
          <svg
            viewBox={`0 0 ${W} ${PIE_H}`}
            className="w-full"
            style={{ height: PIE_H }}
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
                    x: ((e.clientX - rect.left) / rect.width)  * W,
                    y: ((e.clientY - rect.top)  / rect.height) * PIE_H,
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

        {/* Bar hover tooltip */}
        {barTooltip && (
          <div
            className="pointer-events-none absolute z-10 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-lg p-3 text-xs"
            style={{
              left: `${(barTooltip.x / W) * 100}%`,
              top: "8%",
              transform: "translateX(-50%)",
              minWidth: 160,
            }}
          >
            <div className="font-semibold mb-1.5 text-gray-800 dark:text-gray-200">
              {barTooltip.month}
            </div>
            {barTooltip.items.map(item => (
              <div key={item.cat} className="flex justify-between gap-3 text-gray-600 dark:text-gray-400">
                <span>{CATEGORY_EMOJIS[item.cat] ?? "📦"} {item.cat}</span>
                <span className="font-medium text-gray-800 dark:text-gray-200">
                  {gbp.format(item.value)}
                </span>
              </div>
            ))}
            <div className="mt-1.5 pt-1.5 border-t border-gray-100 dark:border-gray-800 flex justify-between font-semibold text-gray-800 dark:text-gray-200">
              <span>Total</span>
              <span>{gbp.format(barTooltip.items.reduce((s, i) => s + i.value, 0))}</span>
            </div>
          </div>
        )}

        {/* Pie hover tooltip */}
        {pieTooltip && (
          <div
            className="pointer-events-none absolute z-10 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-lg p-3 text-xs"
            style={{
              left: `${(pieTooltip.x / W) * 100}%`,
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

      {/* Year navigation (bars & drill-down) */}
      {years.length > 1 && (chartType === "bars" || !!drillCat) && (
        <div className="flex items-center justify-between mt-3">
          <NavBtn
            direction="left"
            onClick={() => {
              if (drillCat) setDrillYearIdx(Math.max(0, actualDrillYearIdx - 1));
              else setYearIdx(Math.max(0, actualYearIdx - 1));
            }}
            disabled={drillCat ? actualDrillYearIdx === 0 : actualYearIdx === 0}
          />
          <span className="text-xs font-medium text-gray-500 tabular-nums">
            {drillCat ? drillYear : selectedYear}
          </span>
          <NavBtn
            direction="right"
            onClick={() => {
              if (drillCat) setDrillYearIdx(Math.min(years.length - 1, actualDrillYearIdx + 1));
              else setYearIdx(Math.min(years.length - 1, actualYearIdx + 1));
            }}
            disabled={drillCat ? actualDrillYearIdx === years.length - 1 : actualYearIdx === years.length - 1}
          />
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
                <span
                  className="w-2.5 h-2.5 rounded-sm shrink-0"
                  style={{ backgroundColor: getCategoryColor(cat) }}
                />
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
