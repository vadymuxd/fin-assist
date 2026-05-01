import {
  computeSavingsDeltas,
  getSavingsAccounts,
  getSavingsSnapshots,
} from "@/lib/queries";
import SavingsKpiCards from "./components/savings-kpi-cards";
import SavingsChart from "./components/savings-chart";
import SavingsAllocationChart from "./components/savings-allocation-chart";
import SavingsAccountsTable from "./components/savings-accounts-table";

export const revalidate = 300;

export default async function SavingsPage() {
  const [snapshots, accounts] = await Promise.all([
    getSavingsSnapshots().catch(() => [] as Awaited<ReturnType<typeof getSavingsSnapshots>>),
    getSavingsAccounts().catch(() => [] as Awaited<ReturnType<typeof getSavingsAccounts>>),
  ]);
  const deltas = computeSavingsDeltas(snapshots);

  return (
    <div className="space-y-4 sm:space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg sm:text-xl font-semibold text-gray-900 dark:text-gray-50">Savings</h1>
        {deltas && (
          <span className="text-xs text-gray-500 dark:text-gray-400">
            Updated {new Date(`${deltas.latest.date}T00:00:00Z`).toLocaleDateString("en-GB", {
              day: "2-digit",
              month: "short",
              year: "numeric",
              timeZone: "UTC",
            })}
          </span>
        )}
      </div>
      <SavingsKpiCards deltas={deltas} />
      <SavingsChart snapshots={snapshots} />
      <SavingsAllocationChart accounts={accounts} />
      <SavingsAccountsTable accounts={accounts} />
    </div>
  );
}
