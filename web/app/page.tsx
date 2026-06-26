import { computeDeltas, getHoldingsWithSectors, getPortfolioSnapshots } from "@/lib/queries";
import KpiCards from "./components/kpi-cards";
import PortfolioChart from "./components/portfolio-chart";
import AllocationChart from "./components/allocation-chart";
import HoldingsTable from "./components/holdings-table";
import Link from "next/link";
import { Compass } from "lucide-react";

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
        <h1 className="text-lg sm:text-xl font-semibold text-gray-900 dark:text-gray-50">Investments</h1>
        <div className="flex items-center gap-3">
          {deltas && (
            <span className="text-xs text-gray-500 dark:text-gray-400">
              Updated {new Date(`${deltas.latest.date}T00:00:00Z`).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" })}
            </span>
          )}
          <Link
            href="/insights"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
          >
            <Compass size={13} strokeWidth={2} />
            Insights
          </Link>
        </div>
      </div>
      <KpiCards deltas={deltas} />
      <PortfolioChart snapshots={snapshots} />
      <AllocationChart holdings={holdings} managed={deltas?.latest.managed} cash={deltas?.latest.cash} />
      <HoldingsTable holdings={holdings} snapshots={snapshots} />
    </div>
  );
}
