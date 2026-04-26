"use client";

import { useMemo, useState } from "react";
import type { SavingsAccount } from "@/lib/queries";

type SortKey = "bank" | "account_name" | "account_type" | "owner" | "balance_gbp";

const gbp = new Intl.NumberFormat("en-GB", {
  style: "currency",
  currency: "GBP",
  maximumFractionDigits: 0,
});

function ownerBadge(owner: string) {
  const isJoint = owner.toLowerCase() === "joint";
  return (
    <span
      className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium ${
        isJoint
          ? "bg-emerald-100 dark:bg-emerald-500/15 text-emerald-700 dark:text-emerald-300"
          : "bg-indigo-100 dark:bg-indigo-500/15 text-indigo-700 dark:text-indigo-300"
      }`}
    >
      {owner}
    </span>
  );
}

export default function SavingsAccountsTable({ accounts }: { accounts: SavingsAccount[] }) {
  const [sortKey, setSortKey] = useState<SortKey>("balance_gbp");
  const [sortAsc, setSortAsc] = useState(false);

  const sorted = useMemo(() => {
    return [...accounts].sort((a, b) => {
      const av = a[sortKey] ?? "";
      const bv = b[sortKey] ?? "";
      const cmp = typeof av === "number" && typeof bv === "number"
        ? av - bv
        : String(av).localeCompare(String(bv));
      return sortAsc ? cmp : -cmp;
    });
  }, [accounts, sortKey, sortAsc]);

  function toggle(key: SortKey) {
    if (sortKey === key) {
      setSortAsc((v) => !v);
    } else {
      setSortKey(key);
      setSortAsc(key !== "balance_gbp");
    }
  }

  function Th({ label, k }: { label: string; k: SortKey }) {
    const active = sortKey === k;
    return (
      <th
        onClick={() => toggle(k)}
        className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400 cursor-pointer select-none whitespace-nowrap hover:text-gray-900 dark:hover:text-gray-50 transition-colors"
      >
        {label} {active ? (sortAsc ? "↑" : "↓") : ""}
      </th>
    );
  }

  if (accounts.length === 0) {
    return (
      <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-6 text-center text-sm text-gray-500 dark:text-gray-400">
        No savings accounts yet.
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 shadow-sm overflow-hidden">
      <div className="px-4 sm:px-6 py-4 border-b border-gray-200 dark:border-gray-800">
        <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">Accounts</h2>
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">Latest snapshot</p>
      </div>

      {/* Desktop table */}
      <div className="hidden sm:block overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="border-b border-gray-200 dark:border-gray-800">
            <tr>
              <Th label="Bank" k="bank" />
              <Th label="Account" k="account_name" />
              <Th label="Type" k="account_type" />
              <Th label="Owner" k="owner" />
              <th className="px-3 py-2 text-right text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400 cursor-pointer select-none hover:text-gray-900 dark:hover:text-gray-50 transition-colors" onClick={() => toggle("balance_gbp")}>
                Balance {sortKey === "balance_gbp" ? (sortAsc ? "↑" : "↓") : ""}
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
            {sorted.map((a) => (
              <tr key={a.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors">
                <td className="px-3 py-2.5 font-medium text-gray-900 dark:text-gray-50 whitespace-nowrap">{a.bank}</td>
                <td className="px-3 py-2.5 text-gray-700 dark:text-gray-300">{a.account_name}</td>
                <td className="px-3 py-2.5 text-gray-500 dark:text-gray-400 capitalize">{a.account_type ?? "—"}</td>
                <td className="px-3 py-2.5">{ownerBadge(a.owner)}</td>
                <td className="px-3 py-2.5 text-right font-medium tabular-nums text-gray-900 dark:text-gray-50">{gbp.format(a.balance_gbp)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile card list */}
      <div className="sm:hidden divide-y divide-gray-100 dark:divide-gray-800">
        {sorted.map((a) => (
          <div key={a.id} className="px-4 py-3 flex items-center justify-between gap-3">
            <div className="min-w-0">
              <div className="font-medium text-sm text-gray-900 dark:text-gray-50 truncate">{a.bank}</div>
              <div className="text-xs text-gray-500 dark:text-gray-400 truncate">{a.account_name}</div>
              <div className="mt-1 flex items-center gap-1.5">{ownerBadge(a.owner)}</div>
            </div>
            <div className="text-right shrink-0">
              <div className="font-medium tabular-nums text-sm text-gray-900 dark:text-gray-50">{gbp.format(a.balance_gbp)}</div>
              {a.account_type && <div className="text-[10px] text-gray-400 dark:text-gray-500 capitalize mt-0.5">{a.account_type}</div>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
