import { getSpendingData } from "@/lib/queries";
import SpendingClient from "./components/spending-client";

export const revalidate = 300;
export const metadata = { title: "Spending" };

export default async function SpendingPage() {
  const data = await getSpendingData().catch(() => ({
    personal: { byCategory: [], monthly: [], daily: [], topMerchants: [], recurring: [] },
    joint:    { byCategory: [], monthly: [], daily: [], topMerchants: [], recurring: [] },
    all:      { byCategory: [], monthly: [], daily: [], topMerchants: [], recurring: [] },
  }));

  return (
    <div className="space-y-4">
      <h1 className="text-lg sm:text-xl font-semibold text-gray-900 dark:text-gray-50">Spending</h1>
      <SpendingClient data={data} />
    </div>
  );
}
