"use client";

import { useRouter, useSearchParams, usePathname } from "next/navigation";
import { useCallback, useTransition, useState, useRef, useEffect } from "react";
import { type MonzoTransaction, type MonzoFilters } from "@/lib/queries";
import { getCategoryEmoji } from "@/lib/category-emojis";
import {
  Search, ChevronLeft, ChevronRight, SlidersHorizontal,
  Users, Tag, CalendarDays, X, ChevronDown, Layers,
} from "lucide-react";

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

function fmtDateHeader(d: string) {
  const date = new Date(d + "T12:00:00");
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);

  const isSameDay = (a: Date, b: Date) =>
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate();

  if (isSameDay(date, today)) return "Today";
  if (isSameDay(date, yesterday)) return "Yesterday";

  return date.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", year: "numeric" });
}

function groupByDate(rows: MonzoTransaction[]): { date: string; rows: MonzoTransaction[] }[] {
  const groups: { date: string; rows: MonzoTransaction[] }[] = [];
  let current: { date: string; rows: MonzoTransaction[] } | null = null;
  for (const row of rows) {
    const d = row.date ?? "Unknown";
    if (!current || current.date !== d) {
      current = { date: d, rows: [] };
      groups.push(current);
    }
    current.rows.push(row);
  }
  return groups;
}

function dayTotal(rows: MonzoTransaction[]) {
  const t = rows.reduce((s, r) => s + (r.amount ?? 0), 0);
  return t;
}

// ── Filter pill ───────────────────────────────────────────────────────────────

type FilterPillProps = {
  icon: React.ReactNode;
  label: string;
  active: boolean;
  onClear: () => void;
  align?: "left" | "right";
  children: React.ReactNode;
};

function FilterPill({ icon, label, active, onClear, align = "left", children }: FilterPillProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    if (open) document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  return (
    <div ref={ref} className="relative shrink-0">
      <button
        onClick={() => setOpen((v) => !v)}
        className={`inline-flex items-center gap-1 px-2.5 h-8 rounded-full text-xs font-medium transition-colors border ${
          active
            ? "bg-blue-50 dark:bg-blue-950 border-blue-300 dark:border-blue-700 text-blue-700 dark:text-blue-300"
            : "bg-white dark:bg-gray-900 border-gray-200 dark:border-gray-800 text-gray-600 dark:text-gray-400 hover:border-gray-300 dark:hover:border-gray-700"
        }`}
      >
        {icon}
        <span className="hidden sm:inline">{label}</span>
        {active ? (
          <span
            role="button"
            onClick={(e) => { e.stopPropagation(); onClear(); setOpen(false); }}
            className="ml-0.5 text-blue-500 hover:text-blue-700"
          >
            <X size={10} strokeWidth={2.5} />
          </span>
        ) : (
          <ChevronDown size={10} strokeWidth={2.5} className="opacity-50" />
        )}
      </button>
      {open && (
        <div className={`absolute top-full mt-1.5 z-50 min-w-[180px] rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-950 shadow-lg p-3 ${align === "right" ? "right-0" : "left-0"}`}>
          {children}
        </div>
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function TransactionsClient({ rows, total, filters }: Props) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [pending, startTransition] = useTransition();
  const searchRef = useRef<HTMLInputElement>(null);

  const perPage = filters.perPage ?? 50;
  const page = filters.page ?? 1;
  const totalPages = Math.max(1, Math.ceil(total / perPage));

  const activeFilterCount = [
    filters.account, filters.category, filters.type,
    filters.dateFrom || filters.dateTo,
  ].filter(Boolean).length;

  const updateParams = useCallback(
    (updates: Record<string, string | undefined>) => {
      const p = new URLSearchParams(searchParams.toString());
      for (const [k, v] of Object.entries(updates)) {
        if (v) p.set(k, v); else p.delete(k);
      }
      p.delete("page");
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

  const clearAll = useCallback(() => {
    updateParams({
      account: undefined, category: undefined, type: undefined,
      dateFrom: undefined, dateTo: undefined, search: undefined,
      amountMin: undefined, amountMax: undefined,
    });
    if (searchRef.current) searchRef.current.value = "";
  }, [updateParams]);

  const groups = groupByDate(rows);

  return (
    <div className={`flex flex-col gap-3 transition-opacity ${pending ? "opacity-60 pointer-events-none" : ""}`}>

      {/* ── Search + filter pills ── */}
      <div className="flex flex-col gap-2">
        {/* Search */}
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
          <input
            ref={searchRef}
            type="search"
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
            className="w-full pl-9 pr-3 h-10 text-sm rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-400"
          />
        </div>

        {/* Filter pills row */}
        <div className="flex items-center gap-1.5 flex-wrap">
          <SlidersHorizontal size={13} className="shrink-0 text-gray-400 ml-0.5" />

          {/* Account */}
          <FilterPill
            icon={<Users size={11} strokeWidth={2} />}
            label={filters.account ? (filters.account === "personal" ? "Personal" : "Joint") : "Account"}
            active={!!filters.account}
            onClear={() => updateParams({ account: undefined })}
          >
            <div className="flex flex-col gap-1">
              {[{ v: undefined, l: "All accounts" }, { v: "personal", l: "Personal" }, { v: "joint", l: "Joint" }].map(({ v, l }) => (
                <button
                  key={l}
                  onClick={() => updateParams({ account: v })}
                  className={`text-left text-sm px-2 py-1.5 rounded-lg transition-colors ${
                    (v ?? "") === (filters.account ?? "")
                      ? "bg-blue-50 dark:bg-blue-950 text-blue-700 dark:text-blue-300 font-medium"
                      : "text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-900"
                  }`}
                >{l}</button>
              ))}
            </div>
          </FilterPill>

          {/* Category */}
          <FilterPill
            icon={<Tag size={11} strokeWidth={2} />}
            label={filters.category ?? "Category"}
            active={!!filters.category}
            onClear={() => updateParams({ category: undefined })}
          >
            <div className="flex flex-col gap-0.5 max-h-56 overflow-y-auto">
              <button
                onClick={() => updateParams({ category: undefined })}
                className={`text-left text-sm px-2 py-1.5 rounded-lg transition-colors ${
                  !filters.category ? "bg-blue-50 dark:bg-blue-950 text-blue-700 dark:text-blue-300 font-medium" : "text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-900"
                }`}
              >All categories</button>
              {CATEGORIES.map((c) => (
                <button
                  key={c}
                  onClick={() => updateParams({ category: c })}
                  className={`text-left text-sm px-2 py-1.5 rounded-lg transition-colors ${
                    filters.category === c ? "bg-blue-50 dark:bg-blue-950 text-blue-700 dark:text-blue-300 font-medium" : "text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-900"
                  }`}
                >{c}</button>
              ))}
            </div>
          </FilterPill>

          {/* Type */}
          <FilterPill
            icon={<Layers size={11} strokeWidth={2} />}
            label={filters.type ?? "Type"}
            active={!!filters.type}
            onClear={() => updateParams({ type: undefined })}
          >
            <div className="flex flex-col gap-0.5">
              <button
                onClick={() => updateParams({ type: undefined })}
                className={`text-left text-sm px-2 py-1.5 rounded-lg transition-colors ${
                  !filters.type ? "bg-blue-50 dark:bg-blue-950 text-blue-700 dark:text-blue-300 font-medium" : "text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-900"
                }`}
              >All types</button>
              {TYPES.map((t) => (
                <button
                  key={t}
                  onClick={() => updateParams({ type: t })}
                  className={`text-left text-sm px-2 py-1.5 rounded-lg transition-colors ${
                    filters.type === t ? "bg-blue-50 dark:bg-blue-950 text-blue-700 dark:text-blue-300 font-medium" : "text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-900"
                  }`}
                >{t}</button>
              ))}
            </div>
          </FilterPill>

          {/* Date */}
          <FilterPill
            align="right"
            icon={<CalendarDays size={11} strokeWidth={2} />}
            label={
              filters.dateFrom && filters.dateTo
                ? `${filters.dateFrom} – ${filters.dateTo}`
                : filters.dateFrom
                ? `From ${filters.dateFrom}`
                : filters.dateTo
                ? `To ${filters.dateTo}`
                : "Date"
            }
            active={!!(filters.dateFrom || filters.dateTo)}
            onClear={() => updateParams({ dateFrom: undefined, dateTo: undefined })}
          >
            <div className="flex flex-col gap-2 min-w-[200px]">
              <label className="text-xs text-gray-500 dark:text-gray-400 font-medium">From</label>
              <input
                type="date"
                value={filters.dateFrom ?? ""}
                onChange={(e) => updateParams({ dateFrom: e.target.value || undefined })}
                className="h-8 px-2 text-sm rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
              <label className="text-xs text-gray-500 dark:text-gray-400 font-medium">To</label>
              <input
                type="date"
                value={filters.dateTo ?? ""}
                onChange={(e) => updateParams({ dateTo: e.target.value || undefined })}
                className="h-8 px-2 text-sm rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
          </FilterPill>

          {/* Clear all */}
          {activeFilterCount > 0 && (
            <button
              onClick={clearAll}
              className="inline-flex items-center gap-1 px-2.5 h-8 rounded-full text-xs font-medium text-gray-500 hover:text-gray-900 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors ml-auto shrink-0"
            >
              <X size={11} strokeWidth={2.5} />
              Clear
            </button>
          )}

          <span className="ml-auto shrink-0 text-xs text-gray-400 pr-0.5">
            {total.toLocaleString()}
          </span>
        </div>
      </div>

      {/* ── Day-grouped list ── */}
      <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-950 overflow-hidden">
        {rows.length === 0 ? (
          <div className="py-12 text-center text-sm text-gray-400">No transactions found</div>
        ) : (
          groups.map((group) => {
            const net = dayTotal(group.rows);
            const netStr = net >= 0
              ? `+£${net.toFixed(2)}`
              : `-£${Math.abs(net).toFixed(2)}`;
            return (
              <div key={group.date}>
                {/* Day header */}
                <div className="flex items-center justify-between px-3.5 py-2 bg-gray-50 dark:bg-gray-900/60 border-b border-gray-100 dark:border-gray-800/80">
                  <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 tracking-wide uppercase">
                    {fmtDateHeader(group.date)}
                  </span>
                  <span className={`text-xs font-medium tabular-nums ${
                    net >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-gray-400 dark:text-gray-500"
                  }`}>
                    {netStr}
                  </span>
                </div>
                {/* Rows */}
                <div className="divide-y divide-gray-50 dark:divide-gray-900">
                  {group.rows.map((row) => {
                    const positive = (row.amount ?? 0) > 0;
                    return (
                      <div
                        key={`${row.transaction_id}-${row.account_type}`}
                        className="flex items-center gap-3 px-3.5 py-3 hover:bg-gray-50/80 dark:hover:bg-gray-900/40 transition-colors"
                      >
                        {/* Emoji avatar */}
                        <div className="w-8 h-8 rounded-full bg-gray-100 dark:bg-gray-800 flex items-center justify-center text-base shrink-0 select-none">
                          {row.emoji ? (
                            <span>{row.emoji}</span>
                          ) : row.category ? (
                            <span>{getCategoryEmoji(row.category)}</span>
                          ) : (
                            <span className="text-gray-400 text-xs font-bold">
                              {(row.name ?? "?")[0]?.toUpperCase()}
                            </span>
                          )}
                        </div>

                        {/* Name + meta */}
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-1.5 min-w-0">
                            <span className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                              {row.name ?? "–"}
                            </span>
                            {/* Account badge — small, desktop only */}
                            <span className={`hidden sm:inline text-[10px] px-1.5 py-0.5 rounded font-medium shrink-0 ${
                              row.account_type === "personal"
                                ? "bg-blue-50 dark:bg-blue-950 text-blue-600 dark:text-blue-400"
                                : "bg-violet-50 dark:bg-violet-950 text-violet-600 dark:text-violet-400"
                            }`}>
                              {row.account_type === "personal" ? "P" : "J"}
                            </span>
                          </div>
                          <div className="flex items-center gap-1.5 mt-0.5 min-w-0">
                            {row.category && (
                              <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 shrink-0">
                                {row.category}
                              </span>
                            )}
                            {row.notes && (
                              <span className="text-xs text-gray-400 truncate">{row.notes}</span>
                            )}
                          </div>
                        </div>

                        {/* Amount */}
                        <span className={`text-sm font-semibold tabular-nums shrink-0 ${
                          positive
                            ? "text-emerald-600 dark:text-emerald-400"
                            : "text-gray-800 dark:text-gray-200"
                        }`}>
                          {fmt(row.amount, row.currency)}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* ── Pagination ── */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm">
          <span className="text-gray-400 text-xs">
            Page {page} of {totalPages}
          </span>
          <div className="flex items-center gap-1.5">
            <button
              onClick={() => goPage(page - 1)}
              disabled={page <= 1}
              className="inline-flex items-center justify-center w-8 h-8 rounded-lg border border-gray-200 dark:border-gray-800 disabled:opacity-30 hover:bg-gray-50 dark:hover:bg-gray-900 transition-colors"
            >
              <ChevronLeft size={14} />
            </button>
            <button
              onClick={() => goPage(page + 1)}
              disabled={page >= totalPages}
              className="inline-flex items-center justify-center w-8 h-8 rounded-lg border border-gray-200 dark:border-gray-800 disabled:opacity-30 hover:bg-gray-50 dark:hover:bg-gray-900 transition-colors"
            >
              <ChevronRight size={14} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
