"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import type { Holding } from "@/lib/queries";
import TickerLogo from "./ticker-logo";

type SortKey = "ticker" | "platform" | "sector" | "market" | "value_gbp" | "pnl_abs" | "pnl_pct";
type Dir = "asc" | "desc";

const gbp = new Intl.NumberFormat("en-GB", {
  style: "currency",
  currency: "GBP",
  maximumFractionDigits: 0,
});

function fmtPct(v: number | null) {
  if (v === null || v === undefined) return "—";
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toFixed(2)}%`;
}

function fmtAbs(v: number | null) {
  if (v === null || v === undefined) return "—";
  const sign = v >= 0 ? "+" : "−";
  return `${sign}${gbp.format(Math.abs(v))}`;
}

function pnlColor(v: number | null) {
  if (v === null || v === undefined) return "text-gray-500";
  if (v > 0) return "text-emerald-600 dark:text-emerald-400";
  if (v < 0) return "text-rose-600 dark:text-rose-400";
  return "text-gray-500 dark:text-gray-400";
}

function compare(a: unknown, b: unknown, dir: Dir) {
  if (a === null || a === undefined) return 1;
  if (b === null || b === undefined) return -1;
  if (typeof a === "number" && typeof b === "number") {
    return dir === "asc" ? a - b : b - a;
  }
  return dir === "asc" ? String(a).localeCompare(String(b)) : String(b).localeCompare(String(a));
}

function SortHeader({
  label,
  k,
  sortKey,
  dir,
  onSort,
  align = "left",
}: {
  label: string;
  k: SortKey;
  sortKey: SortKey;
  dir: Dir;
  onSort: (k: SortKey) => void;
  align?: "left" | "right";
}) {
  const active = sortKey === k;
  return (
    <th
      className={`px-3 py-2.5 text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400 select-none ${
        align === "right" ? "text-right" : "text-left"
      }`}
    >
      <button
        onClick={() => onSort(k)}
        className={`inline-flex items-center gap-1 hover:text-gray-900 dark:hover:text-gray-50 transition-colors ${
          active ? "text-gray-900 dark:text-gray-50" : ""
        }`}
      >
        {label}
        {active && <span className="text-[10px]">{dir === "asc" ? "▲" : "▼"}</span>}
      </button>
    </th>
  );
}

export default function HoldingsTable({ holdings }: { holdings: Holding[] }) {
  const [sortKey, setSortKey] = useState<SortKey>("value_gbp");
  const [dir, setDir] = useState<Dir>("desc");

  const sorted = useMemo(() => {
    return [...holdings].sort((a, b) => compare(a[sortKey], b[sortKey], dir));
  }, [holdings, sortKey, dir]);

  const onSort = (k: SortKey) => {
    if (k === sortKey) {
      setDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(k);
      setDir(k === "ticker" || k === "platform" || k === "sector" || k === "market" ? "asc" : "desc");
    }
  };

  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 overflow-hidden">
      <div className="px-4 sm:px-6 py-4 border-b border-gray-200 dark:border-gray-800">
        <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-50">Holdings</h2>
      </div>

      {/* Desktop table */}
      <div className="hidden sm:block overflow-x-auto">
        <table className="w-full">
          <thead className="bg-gray-50 dark:bg-gray-950/50">
            <tr>
              <SortHeader label="Ticker" k="ticker" sortKey={sortKey} dir={dir} onSort={onSort} />
              <SortHeader label="Platform" k="platform" sortKey={sortKey} dir={dir} onSort={onSort} />
              <SortHeader label="Sector" k="sector" sortKey={sortKey} dir={dir} onSort={onSort} />
              <SortHeader label="Market" k="market" sortKey={sortKey} dir={dir} onSort={onSort} />
              <SortHeader label="Value" k="value_gbp" sortKey={sortKey} dir={dir} onSort={onSort} align="right" />
              <SortHeader label="P&L" k="pnl_abs" sortKey={sortKey} dir={dir} onSort={onSort} align="right" />
              <SortHeader label="P&L %" k="pnl_pct" sortKey={sortKey} dir={dir} onSort={onSort} align="right" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
            {sorted.map((h) => (
              <tr key={h.ticker} className="hover:bg-gray-50 dark:hover:bg-gray-800/30 transition-colors">
                <td className="px-3 py-2.5">
                  <Link
                    href={`/holdings/${encodeURIComponent(h.ticker)}`}
                    className="flex items-center gap-2 hover:underline"
                  >
                    <TickerLogo ticker={h.ticker} size={28} />
                    <div>
                      <div className="font-medium text-gray-900 dark:text-gray-50">{h.ticker}</div>
                      {h.name && (
                        <div className="text-xs text-gray-500 dark:text-gray-400 truncate max-w-[180px]">{h.name}</div>
                      )}
                    </div>
                  </Link>
                </td>
                <td className="px-3 py-2.5 text-sm text-gray-600 dark:text-gray-300">{h.platform ?? "—"}</td>
                <td className="px-3 py-2.5 text-sm text-gray-600 dark:text-gray-300">{h.sector ?? "—"}</td>
                <td className="px-3 py-2.5 text-sm text-gray-600 dark:text-gray-300">{h.market ?? "—"}</td>
                <td className="px-3 py-2.5 text-sm text-right tabular-nums text-gray-900 dark:text-gray-50">
                  {h.value_gbp !== null ? gbp.format(h.value_gbp) : "—"}
                </td>
                <td className={`px-3 py-2.5 text-sm text-right tabular-nums ${pnlColor(h.pnl_abs)}`}>
                  {fmtAbs(h.pnl_abs)}
                </td>
                <td className={`px-3 py-2.5 text-sm text-right tabular-nums ${pnlColor(h.pnl_pct)}`}>
                  {fmtPct(h.pnl_pct)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile card list */}
      <ul className="sm:hidden divide-y divide-gray-100 dark:divide-gray-800">
        {sorted.map((h) => (
          <li key={h.ticker}>
            <Link
              href={`/holdings/${encodeURIComponent(h.ticker)}`}
              className="flex items-center justify-between gap-3 px-4 py-3 active:bg-gray-50 dark:active:bg-gray-800/50"
            >
              <div className="flex items-center gap-3 min-w-0">
                <TickerLogo ticker={h.ticker} size={32} />
                <div className="min-w-0">
                  <div className="font-medium text-gray-900 dark:text-gray-50">{h.ticker}</div>
                  <div className="text-xs text-gray-500 dark:text-gray-400 truncate">
                    {[h.platform, h.sector].filter(Boolean).join(" · ") || "—"}
                  </div>
                </div>
              </div>
              <div className="text-right shrink-0">
                <div className="text-sm tabular-nums text-gray-900 dark:text-gray-50">
                  {h.value_gbp !== null ? gbp.format(h.value_gbp) : "—"}
                </div>
                <div className={`text-xs tabular-nums ${pnlColor(h.pnl_pct)}`}>{fmtPct(h.pnl_pct)}</div>
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
