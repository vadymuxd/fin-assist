"use client";

import { useState } from "react";
import type { MortgageDeltasResult } from "@/lib/queries";

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
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

type DeltaInfo = { absolute: number; pct: number; fromDate: string } | null;

function DeltaCard({ label, delta }: { label: string; delta: DeltaInfo }) {
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
          <div className="mt-1 text-[10px] text-gray-400 dark:text-gray-500">equity since {shortDate(delta.fromDate)}</div>
        </>
      ) : (
        <div className="mt-2 text-xl sm:text-2xl font-semibold tabular-nums text-gray-300 dark:text-gray-700">—</div>
      )}
    </div>
  );
}

export default function MortgageKpiCards({ deltas }: { deltas: MortgageDeltasResult | null }) {
  const [half, setHalf] = useState(false);

  if (!deltas) {
    return (
      <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-6 text-center text-sm text-gray-500 dark:text-gray-400">
        No mortgage data yet. Run <code className="font-mono text-xs">mortgage_snapshot.py --seed</code> to populate.
      </div>
    );
  }

  const { latest, mom, ytd, sinceStart } = deltas;

  const equity     = half ? latest.equity_half      : latest.equity;
  const balance    = half ? latest.balance / 2       : latest.balance;
  const propValue  = half ? latest.property_value / 2 : latest.property_value;
  const ltv        = (latest.balance / latest.property_value) * 100;
  const monthlyRate = latest.rate / 12;
  const interestThisMonth = latest.balance * monthlyRate;
  const principalThisMonth = latest.monthly_payment - interestThisMonth;

  return (
    <div className="space-y-3 sm:space-y-4">
      {/* Hero card */}
      <div className="rounded-xl border border-orange-200 dark:border-orange-900/50 bg-gradient-to-br from-white to-orange-50/40 dark:from-gray-900 dark:to-orange-950/20 p-5 sm:p-6 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
          <div className="flex-1 min-w-0">
            {/* Full / Half toggle */}
            <div className="flex items-center gap-2 mb-3">
              <div className="flex items-center gap-0.5 bg-gray-100 dark:bg-gray-800 rounded-md p-0.5 self-start">
                {(["Full", "My ½"] as const).map((opt) => {
                  const isHalf = opt === "My ½";
                  return (
                    <button
                      key={opt}
                      onClick={() => setHalf(isHalf)}
                      className={`px-2.5 py-1 text-xs font-medium rounded transition-colors ${
                        half === isHalf
                          ? "bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-50 shadow-sm"
                          : "text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-50"
                      }`}
                    >
                      {opt}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Equity */}
            <div className="text-xs font-medium uppercase tracking-wide text-orange-600 dark:text-orange-400">
              Home Equity
            </div>
            <div className="mt-1 text-3xl sm:text-4xl font-semibold tabular-nums text-gray-900 dark:text-gray-50">
              {gbp.format(equity)}
            </div>
            <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              as of {shortDate(latest.date)}
            </div>
          </div>

          {/* Right side breakdown */}
          <div className="grid grid-cols-2 sm:grid-cols-1 gap-x-6 gap-y-3 sm:text-right">
            <div>
              <div className="text-[10px] uppercase tracking-wide text-gray-400 dark:text-gray-500">Remaining Balance</div>
              <div className="text-sm font-semibold tabular-nums text-rose-600 dark:text-rose-400">{gbp.format(balance)}</div>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-wide text-gray-400 dark:text-gray-500">Property Value</div>
              <div className="text-sm font-medium tabular-nums text-gray-700 dark:text-gray-300">{gbp.format(propValue)}</div>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-wide text-gray-400 dark:text-gray-500">LTV</div>
              <div className="text-sm font-semibold tabular-nums text-gray-700 dark:text-gray-300">{ltv.toFixed(1)}%</div>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-wide text-gray-400 dark:text-gray-500">Rate</div>
              <div className="text-sm font-medium tabular-nums text-gray-700 dark:text-gray-300">{(latest.rate * 100).toFixed(2)}%</div>
            </div>
          </div>
        </div>

        {/* Payment breakdown bar */}
        <div className="mt-4 pt-4 border-t border-orange-100 dark:border-orange-900/30">
          <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400 mb-1.5">
            <span>Monthly payment: <span className="font-medium text-gray-700 dark:text-gray-300">{gbp.format(latest.monthly_payment)}</span></span>
            <span>
              <span className="text-red-600 dark:text-red-400 font-medium">{gbp.format(interestThisMonth)} interest</span>
              {" · "}
              <span className="text-emerald-600 dark:text-emerald-400 font-medium">{gbp.format(principalThisMonth)} principal</span>
            </span>
          </div>
          <div className="h-1.5 rounded-full bg-gray-100 dark:bg-gray-800 overflow-hidden flex gap-px">
            <div
              className="h-full rounded-l-full bg-red-500"
              style={{ width: `${(interestThisMonth / latest.monthly_payment) * 100}%` }}
            />
            <div
              className="h-full rounded-r-full bg-emerald-400"
              style={{ width: `${(principalThisMonth / latest.monthly_payment) * 100}%` }}
            />
          </div>
          <div className="flex justify-between text-[10px] text-gray-400 dark:text-gray-500 mt-1">
            <span>{((interestThisMonth / latest.monthly_payment) * 100).toFixed(0)}% interest</span>
            <span>{((principalThisMonth / latest.monthly_payment) * 100).toFixed(0)}% principal</span>
          </div>
        </div>
      </div>

      {/* Delta cards */}
      <div className="grid grid-cols-3 gap-3 sm:gap-4">
        <DeltaCard label="MoM equity" delta={mom} />
        <DeltaCard label="YTD equity" delta={ytd} />
        <DeltaCard label="Since start" delta={sinceStart} />
      </div>
    </div>
  );
}
