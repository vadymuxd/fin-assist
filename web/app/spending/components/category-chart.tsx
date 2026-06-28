"use client";

import { useState } from "react";
import { type SpendingRow } from "@/lib/queries";
import { CATEGORY_COLORS, CATEGORY_EMOJIS, getCategoryColor } from "@/lib/category-emojis";

type Props = { byCategory: SpendingRow[] };

const gbp = new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP", maximumFractionDigits: 0 });

function monthLabel(m: string) {
  const [year, mon] = m.split("-");
  const d = new Date(Number(year), Number(mon) - 1, 1);
  return d.toLocaleDateString("en-GB", { month: "short", year: "2-digit" });
}

type TooltipData = {
  x: number;
  month: string;
  items: { cat: string; value: number }[];
};

export default function CategoryChart({ byCategory }: Props) {
  const [tooltip, setTooltip] = useState<TooltipData | null>(null);

  const monthSet = new Set<string>();
  const catTotals: Record<string, number> = {};
  for (const row of byCategory) {
    monthSet.add(row.month);
    catTotals[row.category] = (catTotals[row.category] ?? 0) + row.total;
  }

  const allCats = Object.entries(catTotals).sort((a, b) => b[1] - a[1]);
  const topCats = allCats.slice(0, 9).map(([c]) => c);
  const hasOther = allCats.length > 9;
  const visibleCats = hasOther ? [...topCats, "Other"] : topCats;

  const months = [...monthSet].sort();
  const rowByMonthCat = new Map(byCategory.map(r => [`${r.month}|${r.category}`, r.total]));

  // Compute stacked data per month
  const monthData = months.map(m => {
    const rawVals: Record<string, number> = {};
    let other = 0;
    for (const [cat] of allCats) {
      const val = rowByMonthCat.get(`${m}|${cat}`) ?? 0;
      if (topCats.includes(cat)) rawVals[cat] = val;
      else other += val;
    }
    if (hasOther) rawVals["Other"] = Math.round(other * 100) / 100;
    const total = visibleCats.reduce((s, c) => s + (rawVals[c] ?? 0), 0);
    return { month: m, label: monthLabel(m), rawVals, total };
  });

  const maxTotal = Math.max(...monthData.map(d => d.total), 1);
  // Round max up to nearest £1k
  const domainMax = Math.ceil(maxTotal / 1000) * 1000;

  // SVG layout
  const W = 620;
  const H = 240;
  const PAD_LEFT = 44;
  const PAD_RIGHT = 8;
  const PAD_TOP = 8;
  const PAD_BOT = 24;
  const plotW = W - PAD_LEFT - PAD_RIGHT;
  const plotH = H - PAD_TOP - PAD_BOT;

  const barGap = 0.2; // 20% gap
  const barW = (plotW / months.length) * (1 - barGap);
  const bandW = plotW / months.length;

  const scaleY = (v: number) => PAD_TOP + plotH - (v / domainMax) * plotH;

  // Y-axis ticks
  const numTicks = 4;
  const tickStep = domainMax / numTicks;
  const yTicks = Array.from({ length: numTicks + 1 }, (_, i) => i * tickStep);

  // Sparse X-axis labels (every 3rd month for readability)
  const xLabelStep = Math.ceil(months.length / 8);

  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-950 p-4">
      <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">Spending by Category</h2>

      <div className="relative">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="w-full"
          style={{ height: 240 }}
          onMouseLeave={() => setTooltip(null)}
        >
          {/* Y-axis gridlines and labels */}
          {yTicks.map(tick => {
            const y = scaleY(tick);
            return (
              <g key={tick}>
                <line x1={PAD_LEFT} x2={W - PAD_RIGHT} y1={y} y2={y} stroke="currentColor" strokeOpacity={0.08} strokeWidth={1} />
                <text
                  x={PAD_LEFT - 4}
                  y={y}
                  textAnchor="end"
                  dominantBaseline="middle"
                  fontSize={9}
                  fill="currentColor"
                  opacity={0.5}
                >
                  {tick === 0 ? "£0k" : `£${(tick / 1000).toFixed(0)}k`}
                </text>
              </g>
            );
          })}

          {/* Bars */}
          {monthData.map((d, mi) => {
            const x0 = PAD_LEFT + mi * bandW + (bandW - barW) / 2;
            let cumY = scaleY(0);
            return (
              <g
                key={d.month}
                onMouseEnter={() => setTooltip({
                  x: x0 + barW / 2,
                  month: d.label,
                  items: visibleCats.map(c => ({ cat: c, value: d.rawVals[c] ?? 0 })).filter(i => i.value > 0),
                })}
              >
                {visibleCats.map((cat, ci) => {
                  const val = d.rawVals[cat] ?? 0;
                  if (val === 0) return null;
                  const barH = (val / domainMax) * plotH;
                  const y = cumY - barH;
                  cumY = y;
                  const isTop = ci === visibleCats.length - 1 || visibleCats.slice(ci + 1).every(c => (d.rawVals[c] ?? 0) === 0);
                  return (
                    <rect
                      key={cat}
                      x={x0}
                      y={y}
                      width={barW}
                      height={barH}
                      fill={getCategoryColor(cat)}
                      rx={isTop ? 2 : 0}
                      ry={isTop ? 2 : 0}
                    />
                  );
                })}
              </g>
            );
          })}

          {/* X-axis labels */}
          {monthData.map((d, mi) => {
            if (mi % xLabelStep !== 0) return null;
            const x = PAD_LEFT + mi * bandW + bandW / 2;
            return (
              <text
                key={d.month}
                x={x}
                y={H - 4}
                textAnchor="middle"
                fontSize={9}
                fill="currentColor"
                opacity={0.5}
              >
                {d.label}
              </text>
            );
          })}
        </svg>

        {/* Tooltip */}
        {tooltip && (
          <div
            className="pointer-events-none absolute z-10 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-lg p-3 text-xs"
            style={{
              left: `${(tooltip.x / W) * 100}%`,
              top: "10%",
              transform: "translateX(-50%)",
              minWidth: 160,
            }}
          >
            <div className="font-semibold mb-1.5 text-gray-800 dark:text-gray-200">{tooltip.month}</div>
            {tooltip.items.map(item => (
              <div key={item.cat} className="flex justify-between gap-3 text-gray-600 dark:text-gray-400">
                <span>{CATEGORY_EMOJIS[item.cat] ?? "📦"} {item.cat}</span>
                <span className="font-medium text-gray-800 dark:text-gray-200">{gbp.format(item.value)}</span>
              </div>
            ))}
            <div className="mt-1.5 pt-1.5 border-t border-gray-100 dark:border-gray-800 flex justify-between font-semibold text-gray-800 dark:text-gray-200">
              <span>Total</span>
              <span>{gbp.format(tooltip.items.reduce((s, i) => s + i.value, 0))}</span>
            </div>
          </div>
        )}
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-x-3 gap-y-1.5 mt-3">
        {visibleCats.map(cat => (
          <span key={cat} className="flex items-center gap-1 text-xs text-gray-600 dark:text-gray-400">
            <span
              className="inline-block w-2.5 h-2.5 rounded-sm shrink-0"
              style={{ backgroundColor: getCategoryColor(cat) }}
            />
            {CATEGORY_EMOJIS[cat] ?? "📦"} {cat}
          </span>
        ))}
      </div>
    </div>
  );
}
