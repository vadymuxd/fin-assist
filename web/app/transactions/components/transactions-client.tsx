"use client";

import { useRouter, useSearchParams, usePathname } from "next/navigation";
import { useCallback, useTransition } from "react";
import { type MonzoTransaction, type MonzoFilters } from "@/lib/queries";
import { Search, ChevronLeft, ChevronRight } from "lucide-react";

type Props = {
  rows: MonzoTransaction[];
  total: number;
  filters: MonzoFilters;
};

const CATEGORIES = [
  "Eating out", "Groceries", "Entertainment", "Shopping", "Transport",
  "Bills", "General", "Savings", "Transfers", "Cash", "Finances",
  "Family", "Personal care", "Health", "Education", "Holidays",
];

const TYPES = [
  "Card payment", "Faster payment", "Pot transfer", "Direct debit",
  "Bank transfer", "ATM", "Monzo-to-Monzo",
];

function fmt(amount: number | null, currency: string | null) {
  if (amount == null) return "–";
  const sym = currency === "GBP" ? "£" : (currency ?? "");
  const abs = Math.abs(amount).toFixed(2);
  return amount < 0 ? `-${sym}${abs}` : `+${sym}${abs}`;
}

function fmtDate(d: string | null) {
  if (!d) return "–";
  try {
    return new Date(d).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
  } catch {
    return d;
  }
}

export default function TransactionsClient({ rows, total, filters }: Props) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [pending, startTransition] = useTransition();

  const perPage = filters.perPage ?? 50;
  const page = filters.page ?? 1;
  const totalPages = Math.max(1, Math.ceil(total / perPage));

  const updateParams = useCallback(
    (updates: Record<string, string | undefined>) => {
      const p = new URLSearchParams(searchParams.toString());
      for (const [k, v] of Object.entries(updates)) {
        if (v) p.set(k, v);
        else p.delete(k);
      }
      p.delete("page"); // reset to page 1 on any filter change
      startTransition(() => router.push(`${pathname}?${p.toString()}`));
    },
    [router, pathname, searchParams]
  );

  const goPage = useCallback(
    (n: number) => {
      const p = new URLSearchParams(searchParams.toString());
      p.set("page", String(n));
      startTransition(() => router.push(`${pathname}?${p.toString()}`));
    },
    [router, pathname, searchParams]
  );

  return (
    <div className={`flex flex-col gap-3 transition-opacity ${pending ? "opacity-60" : ""}`}>
      {/* Filter toolbar */}
      <div className="flex flex-wrap gap-2 items-center">
        {/* Search */}
        <div className="relative flex-1 min-w-40">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            placeholder="Search name, notes…"
            defaultValue={filters.search ?? ""}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                updateParams({ search: (e.target as HTMLInputElement).value || undefined });
              }
            }}
            onBlur={(e) => {
              const v = e.target.value;
              if (v !== (filters.search ?? "")) updateParams({ search: v || undefined });
            }}
            className="w-full pl-8 pr-3 h-8 text-sm rounded-md border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
        </div>

        {/* Account */}
        <select
          value={filters.account ?? "all"}
          onChange={(e) => updateParams({ account: e.target.value === "all" ? undefined : e.target.value })}
          className="h-8 px-2 text-sm rounded-md border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900"
        >
          <option value="all">All accounts</option>
          <option value="personal">Personal</option>
          <option value="joint">Joint</option>
        </select>

        {/* Category */}
        <select
          value={filters.category ?? ""}
          onChange={(e) => updateParams({ category: e.target.value || undefined })}
          className="h-8 px-2 text-sm rounded-md border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900"
        >
          <option value="">All categories</option>
          {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>

        {/* Type */}
        <select
          value={filters.type ?? ""}
          onChange={(e) => updateParams({ type: e.target.value || undefined })}
          className="h-8 px-2 text-sm rounded-md border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900"
        >
          <option value="">All types</option>
          {TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>

        {/* Date from */}
        <input
          type="date"
          value={filters.dateFrom ?? ""}
          onChange={(e) => updateParams({ dateFrom: e.target.value || undefined })}
          className="h-8 px-2 text-sm rounded-md border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900"
        />
        <span className="text-gray-400 text-sm">–</span>
        <input
          type="date"
          value={filters.dateTo ?? ""}
          onChange={(e) => updateParams({ dateTo: e.target.value || undefined })}
          className="h-8 px-2 text-sm rounded-md border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900"
        />

        <div className="ml-auto text-xs text-gray-400">
          {total.toLocaleString()} transactions
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-950">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100 dark:border-gray-800 text-left text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide">
              <th className="px-3 py-2.5 font-medium">Date</th>
              <th className="px-3 py-2.5 font-medium">Name</th>
              <th className="px-3 py-2.5 font-medium hidden sm:table-cell">Category</th>
              <th className="px-3 py-2.5 font-medium hidden md:table-cell">Type</th>
              <th className="px-3 py-2.5 font-medium hidden md:table-cell">Account</th>
              <th className="px-3 py-2.5 font-medium text-right">Amount</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50 dark:divide-gray-900">
            {rows.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-3 py-8 text-center text-sm text-gray-400">
                  No transactions found
                </td>
              </tr>
            ) : (
              rows.map((row) => {
                const positive = (row.amount ?? 0) > 0;
                return (
                  <tr key={`${row.transaction_id}-${row.account_type}`}
                      className="hover:bg-gray-50 dark:hover:bg-gray-900/50 transition-colors">
                    <td className="px-3 py-2 whitespace-nowrap text-gray-500 dark:text-gray-400 text-xs">
                      {fmtDate(row.date)}
                    </td>
                    <td className="px-3 py-2 max-w-[180px]">
                      <div className="flex items-center gap-1.5 min-w-0">
                        {row.emoji && (
                          <span className="text-base shrink-0">{row.emoji}</span>
                        )}
                        <span className="truncate font-medium text-gray-900 dark:text-gray-100">
                          {row.name ?? "–"}
                        </span>
                      </div>
                      {row.notes && (
                        <div className="text-xs text-gray-400 truncate mt-0.5">{row.notes}</div>
                      )}
                    </td>
                    <td className="px-3 py-2 hidden sm:table-cell">
                      <span className="inline-block text-xs px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300">
                        {row.category ?? "–"}
                      </span>
                    </td>
                    <td className="px-3 py-2 hidden md:table-cell text-xs text-gray-500 dark:text-gray-400">
                      {row.type ?? "–"}
                    </td>
                    <td className="px-3 py-2 hidden md:table-cell">
                      <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${
                        row.account_type === "personal"
                          ? "bg-blue-50 dark:bg-blue-950 text-blue-600 dark:text-blue-400"
                          : "bg-violet-50 dark:bg-violet-950 text-violet-600 dark:text-violet-400"
                      }`}>
                        {row.account_type}
                      </span>
                    </td>
                    <td className={`px-3 py-2 text-right font-medium tabular-nums ${
                      positive
                        ? "text-emerald-600 dark:text-emerald-400"
                        : "text-gray-900 dark:text-gray-100"
                    }`}>
                      {fmt(row.amount, row.currency)}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm">
          <span className="text-gray-500 text-xs">
            Page {page} of {totalPages}
          </span>
          <div className="flex items-center gap-1">
            <button
              onClick={() => goPage(page - 1)}
              disabled={page <= 1}
              className="inline-flex items-center justify-center w-8 h-8 rounded-md border border-gray-200 dark:border-gray-800 disabled:opacity-40 hover:bg-gray-50 dark:hover:bg-gray-900 transition-colors"
            >
              <ChevronLeft size={14} />
            </button>
            <button
              onClick={() => goPage(page + 1)}
              disabled={page >= totalPages}
              className="inline-flex items-center justify-center w-8 h-8 rounded-md border border-gray-200 dark:border-gray-800 disabled:opacity-40 hover:bg-gray-50 dark:hover:bg-gray-900 transition-colors"
            >
              <ChevronRight size={14} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
