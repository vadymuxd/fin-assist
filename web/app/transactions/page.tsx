import { Suspense } from "react";
import Link from "next/link";
import { ChevronLeft } from "lucide-react";
import { getMonzoTransactions, type MonzoFilters } from "@/lib/queries";
import TransactionsClient from "./components/transactions-client";

export const metadata = { title: "Transactions" };

type PageProps = {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
};

function sp(v: string | string[] | undefined): string | undefined {
  return Array.isArray(v) ? v[0] : v;
}

async function TransactionsData({ searchParams }: { searchParams: PageProps["searchParams"] }) {
  const params = await searchParams;

  const filters: MonzoFilters = {
    account:   sp(params.account),
    category:  sp(params.category),
    type:      sp(params.type),
    search:    sp(params.search),
    dateFrom:  sp(params.dateFrom),
    dateTo:    sp(params.dateTo),
    amountMin: sp(params.amountMin),
    amountMax: sp(params.amountMax),
    pot:       sp(params.pot),
    page:      params.page ? parseInt(sp(params.page)!) : 1,
    perPage:   50,
  };

  const { rows, total } = await getMonzoTransactions(filters).catch(() => ({ rows: [], total: 0 }));

  return <TransactionsClient rows={rows} total={total} filters={filters} />;
}

export default function TransactionsPage({ searchParams }: PageProps) {
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Link
          href="/spending"
          className="inline-flex items-center justify-center w-8 h-8 rounded-lg text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          aria-label="Back to Spending"
        >
          <ChevronLeft size={20} strokeWidth={2} />
        </Link>
        <h1 className="text-lg sm:text-xl font-semibold text-gray-900 dark:text-gray-50">
          Transactions
        </h1>
      </div>
      <Suspense fallback={<div className="text-sm text-gray-400 py-8 text-center">Loading…</div>}>
        <TransactionsData searchParams={searchParams} />
      </Suspense>
    </div>
  );
}
