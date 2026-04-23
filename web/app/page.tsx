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
      <KpiCards deltas={deltas} />
      <PortfolioChart snapshots={snapshots} />
      <AllocationChart holdings={holdings} />
      <HoldingsTable holdings={holdings} />
    </div>
  );
}
