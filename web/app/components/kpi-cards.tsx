"use client";

import { useState } from "react";
import type { DashboardDeltas, Delta } from "@/lib/queries";

const gbp = new Intl.NumberFormat("en-GB", {
  style: "currency",
  currency: "GBP",
  maximumFractionDigits: 0,
});

function fmtPct(pct: number): string {
  const sign = pct > 0 ? "+" : "";
  return `${sign}${pct.toFixed(2)}%`;
}

function fmtAbs(abs: number): string {
  const sign = abs >= 0 ? "+" : "−";
  return `${sign}${gbp.format(Math.abs(abs))}`;
}

function deltaColor(pct: number): string {
  if (pct > 0) return "text-emerald-600 dark:text-emerald-400";
  if (pct < 0) return "text-rose-600 dark:text-rose-400";
  return "text-gray-500 dark:text-gray-400";
}

function deltaBg(pct: number): string {
  if (pct > 0) return "bg-emerald-50 dark:bg-emerald-500/10";
  if (pct < 0) return "bg-rose-50 dark:bg-rose-500/10";
  return "bg-gray-50 dark:bg-gray-800";
}

function shortDate(iso: string): string {
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    timeZone: "UTC",
  });
}

function DeltaCard({
  label,
  delta,
  baselineDate,
}: {
  label: string;
  delta: Delta | null;
  baselineDate: string;
}) {
  return (
    <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-4 shadow-sm">
      <div className="flex items-center justify-between">
        <div className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
          {label}
        </div>
        {delta && (
          <span
            className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${deltaBg(delta.pct)} ${deltaColor(
              delta.pct
            )}`}
          >
            {delta.pct >= 0 ? "▲" : "▼"}
          </span>
        )}
      </div>
      {delta ? (
        <>
          <div className={`mt-2 text-xl sm:text-2xl font-semibold tabular-nums ${deltaColor(delta.pct)}`}>
            {fmtPct(delta.pct)}
          </div>
          <div className={`mt-0.5 text-xs tabular-nums ${deltaColor(delta.pct)}`}>
            {fmtAbs(delta.absolute)}
          </div>
          <div className="mt-1 text-[10px] text-gray-400 dark:text-gray-500">
            since {shortDate(delta.fromDate)}
          </div>
        </>
      ) : (
        <>
          <div className="mt-2 text-xl sm:text-2xl font-semibold tabular-nums text-gray-300 dark:text-gray-700">
            —
          </div>
          <div className="mt-0.5 text-[10px] text-gray-400 dark:text-gray-500">
            tracking from {shortDate(baselineDate)}
          </div>
        </>
      )}
    </div>
  );
}

function BreakdownChip({
  label,
  value,
  total,
}: {
  label: string;
  value: number;
  total: number;
}) {
  const pct = total > 0 ? (value / total) * 100 : 0;
  return (
    <div className="flex flex-col">
      <div className="text-[10px] uppercase tracking-wide text-gray-400 dark:text-gray-500">{label}</div>
      <div className="text-sm font-medium tabular-nums text-gray-900 dark:text-gray-50">
        {gbp.format(value)}
      </div>
      <div className="text-[10px] text-gray-400 dark:text-gray-500 tabular-nums">{pct.toFixed(0)}%</div>
    </div>
  );
}

type Owner = "Joint" | "Vadym" | "Lisa";
const OWNERS: Owner[] = ["Joint", "Vadym", "Lisa"];

export default function KpiCards({ deltas }: { deltas: DashboardDeltas | null }) {
  const [owner, setOwner] = useState<Owner>("Vadym");

  if (!deltas) {
    return (
      <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-6 text-center text-sm text-gray-500 dark:text-gray-400">
        No portfolio snapshots yet.
      </div>
    );
  }

  const { latest, baselineDate } = deltas;

  const stocks = latest.self_managed ?? 0;
  const cash = latest.cash ?? 0;
  const managed = latest.managed ?? 0;

  // Use self_managed + managed + cash — same components as the Allocation chart —
  // so both totals agree. vadym_total / joint_total from the sheet exclude cash.
  const total =
    owner === "Joint" ? (latest.joint_total ?? 0)
    : owner === "Lisa" ? (latest.lisa_total ?? 0)
    : stocks + managed + cash;

  const daily =
    owner === "Joint" ? deltas.jointDaily
    : owner === "Lisa" ? deltas.lisaDaily
    : deltas.daily;

  const wow =
    owner === "Joint" ? deltas.jointWow
    : owner === "Lisa" ? deltas.lisaWow
    : deltas.wow;

  const mom =
    owner === "Joint" ? deltas.jointMom
    : owner === "Lisa" ? deltas.lisaMom
    : deltas.mom;

  const sinceBaseline =
    owner === "Joint" ? deltas.jointSinceBaseline
    : owner === "Lisa" ? deltas.lisaSinceBaseline
    : deltas.sinceBaseline;

  return (
    <div className="space-y-3 sm:space-y-4">
      {/* Hero card */}
      <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-gradient-to-br from-white to-gray-50 dark:from-gray-900 dark:to-gray-950 p-5 sm:p-6 shadow-sm">
        <div className="space-y-3">
          {/* Label + segmented control always on the same row */}
          <div className="flex items-center justify-between gap-3">
            <div className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
              {owner} Total
            </div>
            <div className="flex items-center gap-0.5 bg-gray-100 dark:bg-gray-800 rounded-md p-0.5">
              {OWNERS.map((o) => (
                <button
                  key={o}
                  onClick={() => setOwner(o)}
                  className={`px-2.5 py-0.5 text-xs font-medium rounded transition-colors ${
                    owner === o
                      ? "bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-50 shadow-sm"
                      : "text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-50"
                  }`}
                >
                  {o}
                </button>
              ))}
            </div>
          </div>
          {/* Amount + breakdown */}
          <div className="flex items-end justify-between gap-4">
            <div>
              <div className="text-3xl sm:text-4xl font-semibold tabular-nums text-gray-900 dark:text-gray-50">
                {gbp.format(total)}
              </div>
              <div className="mt-1 flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                <span>as of {shortDate(latest.date)}</span>
                {daily && (
                  <>
                    <span className="text-gray-300 dark:text-gray-700">•</span>
                    <span className={`font-medium tabular-nums ${deltaColor(daily.pct)}`}>
                      {daily.pct >= 0 ? "▲" : "▼"} {fmtAbs(daily.absolute)} ({fmtPct(daily.pct)}) today
                    </span>
                  </>
                )}
              </div>
            </div>
            {owner === "Vadym" && (
              <div className="grid grid-cols-3 gap-4 sm:gap-6 shrink-0">
                <BreakdownChip label="Stocks" value={stocks} total={total} />
                <BreakdownChip label="Cash" value={cash} total={total} />
                <BreakdownChip label="Managed" value={managed} total={total} />
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Delta strip */}
      <div className="grid grid-cols-3 gap-3 sm:gap-4">
        <DeltaCard label="WoW" delta={wow} baselineDate={baselineDate} />
        <DeltaCard label="MoM" delta={mom} baselineDate={baselineDate} />
        <DeltaCard label="Start" delta={sinceBaseline} baselineDate={baselineDate} />
      </div>
    </div>
  );
}
