import { computeDeltas, getHoldingsWithSectors, getPortfolioSnapshots } from "@/lib/queries";
import KpiCards from "./components/kpi-cards";
import PortfolioChart from "./components/portfolio-chart";
import AllocationChart from "./components/allocation-chart";
import HoldingsTable from "./components/holdings-table";

export const revalidate = 300;

export default async function DashboardPage() {
  const [snapshots, holdings] = await Promise.all([
    getPortfolioSnapshots(),
    getHoldingsWithSectors(),
  ]);
  const deltas = computeDeltas(snapshots);

  return (
    <div className="space-y-4 sm:space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg sm:text-xl font-semibold text-gray-900 dark:text-gray-50">Dashboard</h1>
        {deltas && (
          <span className="text-xs text-gray-500 dark:text-gray-400">
            Updated {new Date(`${deltas.latest.date}T00:00:00Z`).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" })}
          </span>
        )}
      </div>
      <KpiCards deltas={deltas} />
      <PortfolioChart snapshots={snapshots} />
      <AllocationChart holdings={holdings} />
      <HoldingsTable holdings={holdings} />
    </div>
  );
}
