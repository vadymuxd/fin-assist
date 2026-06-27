"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import type { Holding, HoldingPriceHistoryMap, PortfolioSnapshot } from "@/lib/queries";
import TickerLogo from "./ticker-logo";

type SortKey = "ticker" | "platform" | "sector" | "market" | "value_gbp" | "pnl_abs" | "pnl_pct";
type Dir = "asc" | "desc";
type Period = "W" | "M" | "START";

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

function withComputedPnlPct(h: Holding): Holding {
  const cost = (h.avg_buy ?? 0) * (h.qty ?? 0);
  if (cost > 0 && h.pnl_abs !== null) {
    return { ...h, pnl_pct: (h.pnl_abs / cost) * 100 };
  }
  return h;
}

function daysAgoISO(days: number): string {
  const d = new Date();
  d.setUTCHours(0, 0, 0, 0);
  d.setUTCDate(d.getUTCDate() - days);
  return d.toISOString().slice(0, 10);
}

function findClosestPrice(pts: { date: string; price: number }[], targetDate: string): number | null {
  const candidates = pts.filter((p) => p.date <= targetDate);
  return candidates.length > 0 ? candidates[candidates.length - 1].price : null;
}

function portfolioDelta(snapshots: PortfolioSnapshot[], targetISO: string): number | null {
  if (snapshots.length < 2) return null;
  const sorted = [...snapshots].sort((a, b) => a.date.localeCompare(b.date));
  const latest = sorted[sorted.length - 1];
  const candidates = sorted.filter((s) => s.date <= targetISO && s.date < latest.date);
  if (candidates.length === 0) return null;
  const prev = candidates[candidates.length - 1];
  const base = prev.self_managed;
  if (base === 0) return null;
  const organic =
    (latest.self_managed - prev.self_managed) -
    ((latest.stocks_started_value ?? 0) - (prev.stocks_started_value ?? 0));
  return (organic / base) * 100;
}

const PERIOD_LABELS: Record<Period, string> = { W: "WoW", M: "MoM", START: "All time" };

export default function HoldingsTable({
  holdings,
  snapshots = [],
  priceHistoryMap,
}: {
  holdings: Holding[];
  snapshots?: PortfolioSnapshot[];
  priceHistoryMap?: HoldingPriceHistoryMap;
}) {
  const [sortKey, setSortKey] = useState<SortKey>("value_gbp");
  const [dir, setDir] = useState<Dir>("desc");
  const [period, setPeriod] = useState<Period>("START");

  const enriched = useMemo(() => holdings.map(withComputedPnlPct), [holdings]);

  const sorted = useMemo(() => {
    return [...enriched].sort((a, b) => compare(a[sortKey], b[sortKey], dir));
  }, [enriched, sortKey, dir]);

  const onSort = (k: SortKey) => {
    if (k === sortKey) {
      setDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(k);
      setDir(k === "ticker" || k === "platform" || k === "sector" || k === "market" ? "asc" : "desc");
    }
  };

  // Portfolio-level delta for the header badge.
  // START matches the Sheet: aggregate current value vs aggregate tracking-started
  // value. W/M use snapshot deltas (no per-holding history for arbitrary windows).
  const portfolioPct = useMemo(() => {
    if (period === "START") {
      let value = 0;
      let started = 0;
      for (const h of holdings) {
        if (h.value_gbp !== null && h.tracking_started_value) {
          value += h.value_gbp;
          started += h.tracking_started_value;
        }
      }
      return started > 0 ? (value / started - 1) * 100 : null;
    }
    if (period === "W") return portfolioDelta(snapshots, daysAgoISO(7));
    return portfolioDelta(snapshots, daysAgoISO(30));
  }, [snapshots, holdings, period]);

  // Per-holding % derived from price history for all periods
  function rowPct(h: Holding): number | null {
    const current = h.current_price;
    if (current === null) return null;

    const pts = (priceHistoryMap ?? {})[h.ticker] ?? [];

    if (period === "START") {
      // Real money-weighted return since Apr 13 (Sheet col K) — accounts for
      // actual purchase timing, unlike the raw price-window returns below.
      return h.tracking_pnl_pct ?? h.pnl_pct ?? null;
    }
    if (period === "W") {
      const basePrice = findClosestPrice(pts, daysAgoISO(7));
      if (basePrice === null || basePrice === 0) return null;
      return ((current - basePrice) / basePrice) * 100;
    }
    // M
    const basePrice = findClosestPrice(pts, daysAgoISO(30));
    if (basePrice === null || basePrice === 0) return null;
    return ((current - basePrice) / basePrice) * 100;
  }

  const pctColLabel =
    period === "W" ? "7d %" :
    period === "M" ? "30d %" :
    "Since 13 Apr";

  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 overflow-hidden">
      <div className="px-4 sm:px-6 py-4 border-b border-gray-200 dark:border-gray-800 flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-50">Holdings</h2>
          {portfolioPct !== null && (
            <span className={`text-[11px] font-medium px-2 py-0.5 rounded-full ${
              portfolioPct >= 0
                ? "bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                : "bg-rose-50 dark:bg-rose-500/10 text-rose-600 dark:text-rose-400"
            }`}>
              Portfolio {portfolioPct >= 0 ? "+" : ""}{portfolioPct.toFixed(2)}%{" "}
              {period === "W" ? "this week" : period === "M" ? "this month" : "since 13 Apr"}
            </span>
          )}
        </div>
        {/* Period segmented control */}
        <div className="flex items-center gap-0.5 bg-gray-100 dark:bg-gray-800 rounded-md p-0.5">
          {(["W", "M", "START"] as Period[]).map((p) => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`px-2.5 py-1 text-xs font-medium rounded transition-colors ${
                period === p
                  ? "bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-50 shadow-sm"
                  : "text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-50"
              }`}
              title={PERIOD_LABELS[p]}
            >
              {p}
            </button>
          ))}
        </div>
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
              <SortHeader label={pctColLabel} k="pnl_pct" sortKey={sortKey} dir={dir} onSort={onSort} align="right" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
            {sorted.map((h) => {
              const pct = rowPct(h);
              return (
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
                    {period === "START" ? fmtAbs(h.pnl_abs) : "—"}
                  </td>
                  <td className={`px-3 py-2.5 text-sm text-right tabular-nums ${pnlColor(pct)}`}>
                    {fmtPct(pct)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Mobile card list */}
      <ul className="sm:hidden divide-y divide-gray-100 dark:divide-gray-800">
        {sorted.map((h) => {
          const pct = rowPct(h);
          return (
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
                  <div className={`text-xs tabular-nums ${pnlColor(pct)}`}>{fmtPct(pct)}</div>
                </div>
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
