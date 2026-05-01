import {
  computePensionDeltas,
  getPensionAccounts,
  getPensionSnapshots,
} from "@/lib/queries";
import PensionKpiCards from "./components/pension-kpi-cards";
import PensionChart from "./components/pension-chart";
import PensionAllocationChart from "./components/pension-allocation-chart";
import PensionAccountsTable from "./components/pension-accounts-table";

export const revalidate = 300;

export default async function PensionsPage() {
  const [snapshots, accounts] = await Promise.all([
    getPensionSnapshots().catch(() => [] as Awaited<ReturnType<typeof getPensionSnapshots>>),
    getPensionAccounts().catch(() => [] as Awaited<ReturnType<typeof getPensionAccounts>>),
  ]);
  const deltas = computePensionDeltas(snapshots);

  return (
    <div className="space-y-4 sm:space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg sm:text-xl font-semibold text-gray-900 dark:text-gray-50">Pensions</h1>
        {deltas && (
          <span className="text-xs text-gray-500 dark:text-gray-400">
            Updated{" "}
            {new Date(`${deltas.latest.date}T00:00:00Z`).toLocaleDateString("en-GB", {
              day: "2-digit",
              month: "short",
              year: "numeric",
              timeZone: "UTC",
            })}
          </span>
        )}
      </div>
      <PensionKpiCards deltas={deltas} />
      <PensionChart snapshots={snapshots} />
      <PensionAllocationChart accounts={accounts} />
      <PensionAccountsTable accounts={accounts} />
    </div>
  );
}
