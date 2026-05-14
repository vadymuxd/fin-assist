"use client";

import { useState } from "react";
import type { NetWorthPoint } from "@/lib/queries";

type Owner = "Joint" | "Vadym" | "Lisa";
const OWNERS: Owner[] = ["Joint", "Vadym", "Lisa"];

const gbp = new Intl.NumberFormat("en-GB", {
  style: "currency",
  currency: "GBP",
  maximumFractionDigits: 0,
});

function fmtPct(pct: number) {
  return `${pct > 0 ? "+" : ""}${pct.toFixed(2)}%`;
}
function fmtAbs(abs: number) {
  return `${abs >= 0 ? "+" : "−"}${gbp.format(Math.abs(abs))}`;
}
function deltaColor(pct: number) {
  if (pct > 0) return "text-emerald-600 dark:text-emerald-400";
  if (pct < 0) return "text-rose-600 dark:text-rose-400";
  return "text-gray-500 dark:text-gray-400";
}
function deltaBg(pct: number) {
  if (pct > 0) return "bg-emerald-50 dark:bg-emerald-500/10";
  if (pct < 0) return "bg-rose-50 dark:bg-rose-500/10";
  return "bg-gray-50 dark:bg-gray-800";
}
function shortDate(iso: string) {
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    timeZone: "UTC",
  });
}

type DeltaInfo = { absolute: number; pct: number; fromDate: string } | null;

function computeDelta(latest: number, prevVal: number | null, prevDate: string | null): DeltaInfo {
  if (prevVal === null || prevDate === null) return null;
  const absolute = latest - prevVal;
  const pct = prevVal === 0 ? 0 : (absolute / prevVal) * 100;
  return { absolute, pct, fromDate: prevDate };
}

function daysAgoISO(days: number) {
  const d = new Date();
  d.setUTCHours(0, 0, 0, 0);
  d.setUTCDate(d.getUTCDate() - days);
  return d.toISOString().slice(0, 10);
}

function findOnOrBefore(points: NetWorthPoint[], target: string): NetWorthPoint | null {
  const c = points.filter((p) => p.date <= target);
  return c.length === 0 ? null : c[c.length - 1];
}

function getOwnerValue(p: NetWorthPoint, owner: Owner): number {
  if (owner === "Vadym") return p.vadym_net_worth;
  if (owner === "Lisa")  return p.lisa_net_worth;
  return p.net_worth;
}

function DeltaCard({ label, delta, baselineDate }: { label: string; delta: DeltaInfo; baselineDate: string }) {
  return (
    <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-4 shadow-sm">
      <div className="flex items-center justify-between">
        <div className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">{label}</div>
        {delta && (
          <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${deltaBg(delta.pct)} ${deltaColor(delta.pct)}`}>
            {delta.pct >= 0 ? "▲" : "▼"}
          </span>
        )}
      </div>
      {delta ? (
        <>
          <div className={`mt-2 text-xl sm:text-2xl font-semibold tabular-nums ${deltaColor(delta.pct)}`}>
            {fmtPct(delta.pct)}
          </div>
          <div className={`mt-0.5 text-xs tabular-nums ${deltaColor(delta.pct)}`}>{fmtAbs(delta.absolute)}</div>
          <div className="mt-1 text-[10px] text-gray-400 dark:text-gray-500">since {shortDate(delta.fromDate)}</div>
        </>
      ) : (
        <>
          <div className="mt-2 text-xl sm:text-2xl font-semibold tabular-nums text-gray-300 dark:text-gray-700">—</div>
          <div className="mt-0.5 text-[10px] text-gray-400 dark:text-gray-500">
            tracking from {shortDate(baselineDate)}
          </div>
        </>
      )}
    </div>
  );
}

function BreakdownChip({ label, value, total, color }: { label: string; value: number; total: number; color: string }) {
  const pct = total > 0 ? (value / total) * 100 : 0;
  return (
    <div className="flex flex-col">
      <div className="flex items-center gap-1.5">
        <span className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
        <div className="text-[10px] uppercase tracking-wide text-gray-400 dark:text-gray-500">{label}</div>
      </div>
      <div className="text-sm font-medium tabular-nums text-gray-900 dark:text-gray-50 mt-0.5">{gbp.format(value)}</div>
      <div className="text-[10px] text-gray-400 dark:text-gray-500 tabular-nums">{pct.toFixed(0)}%</div>
    </div>
  );
}

export default function NetWorthKpiCards({ data }: { data: NetWorthPoint[] }) {
  const [owner, setOwner] = useState<Owner>("Joint");

  if (data.length === 0) {
    return (
      <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-6 text-center text-sm text-gray-500 dark:text-gray-400">
        No net worth data yet — run savings and portfolio snapshots to populate.
      </div>
    );
  }

  const sorted = [...data].sort((a, b) => a.date.localeCompare(b.date));
  const latest = sorted[sorted.length - 1];
  const baseline = sorted[0];
  const prior = sorted.slice(0, -1);

  const latestVal = getOwnerValue(latest, owner);

  const wowSnap = findOnOrBefore(prior, daysAgoISO(7));
  const momSnap = findOnOrBefore(prior, daysAgoISO(30));
  const momFallback = prior.length > 0 ? prior[0] : null;

  const wow       = computeDelta(latestVal, wowSnap ? getOwnerValue(wowSnap, owner) : null, daysAgoISO(7));
  const mom       = computeDelta(latestVal, momSnap ? getOwnerValue(momSnap, owner) : null, momSnap?.date ?? momFallback?.date ?? null);
  const sinceStart = baseline.date !== latest.date
    ? computeDelta(latestVal, getOwnerValue(baseline, owner), baseline.date)
    : null;

  const equityHalf = latest.mortgage_equity / 2;

  const chips =
    owner === "Vadym" ? [
      { label: "Investments", value: latest.vadym_investments, color: "#2563eb" },
      { label: "Savings",     value: latest.vadym_savings,     color: "#10b981" },
      { label: "Pensions",    value: latest.vadym_pensions,    color: "#f59e0b" },
      { label: "Mortgage (½)", value: equityHalf,              color: "#f97316" },
    ]
    : owner === "Lisa" ? [
      { label: "Investments", value: latest.lisa_investments, color: "#2563eb" },
      { label: "Savings",     value: latest.lisa_savings,     color: "#10b981" },
      { label: "Pensions",    value: latest.lisa_pensions,    color: "#f59e0b" },
      { label: "Mortgage (½)", value: equityHalf,             color: "#f97316" },
    ]
    : [
      { label: "Investments", value: latest.investments,      color: "#2563eb" },
      { label: "Savings",     value: latest.savings,          color: "#10b981" },
      { label: "Pensions",    value: latest.pensions,         color: "#f59e0b" },
      { label: "Mortgage",    value: latest.mortgage_equity,  color: "#f97316" },
    ];

  return (
    <div className="space-y-3 sm:space-y-4">
      <div className="rounded-xl border border-violet-200 dark:border-violet-900/50 bg-gradient-to-br from-white to-violet-50/40 dark:from-gray-900 dark:to-violet-950/20 p-5 sm:p-6 shadow-sm">
        <div className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <div className="text-xs font-medium uppercase tracking-wide text-violet-600 dark:text-violet-400">
              {owner} Net Worth
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

          <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
            <div>
              <div className="text-3xl sm:text-4xl font-semibold tabular-nums text-gray-900 dark:text-gray-50">
                {gbp.format(latestVal)}
              </div>
              <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                as of {new Date(`${latest.date}T00:00:00Z`).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" })}
              </div>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 sm:gap-6">
              {chips.map((c) => (
                <BreakdownChip key={c.label} label={c.label} value={c.value} total={latestVal} color={c.color} />
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3 sm:gap-4">
        <DeltaCard label="WoW" delta={wow} baselineDate={baseline.date} />
        <DeltaCard label="MoM" delta={mom} baselineDate={baseline.date} />
        <DeltaCard label="Start" delta={sinceStart} baselineDate={baseline.date} />
      </div>
    </div>
  );
}
