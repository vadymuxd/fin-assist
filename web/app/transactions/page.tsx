import { Suspense } from "react";
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
      <h1 className="text-lg sm:text-xl font-semibold text-gray-900 dark:text-gray-50">
        Transactions
      </h1>
      <Suspense fallback={<div className="text-sm text-gray-400 py-8 text-center">Loading…</div>}>
        <TransactionsData searchParams={searchParams} />
      </Suspense>
    </div>
  );
}
