import { computeMortgageDeltas, getMortgageSnapshots } from "@/lib/queries";
import MortgageKpiCards from "./components/mortgage-kpi-cards";
import MortgageChart from "./components/mortgage-chart";
import MortgageMetrics from "./components/mortgage-metrics";

export const revalidate = 300;

export default async function MortgagePage() {
  const snapshots = await getMortgageSnapshots().catch(() => []);
  const deltas = computeMortgageDeltas(snapshots);

  return (
    <div className="space-y-4 sm:space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg sm:text-xl font-semibold text-gray-900 dark:text-gray-50">Mortgage</h1>
        {deltas && (
          <span className="text-xs text-gray-500 dark:text-gray-400">
            Updated {new Date(deltas.latest.updated_at).toLocaleDateString("en-GB", {
              day: "2-digit",
              month: "short",
              year: "numeric",
            })}
          </span>
        )}
      </div>
      <MortgageKpiCards deltas={deltas} />
      <MortgageChart snapshots={snapshots} />
      <MortgageMetrics snapshots={snapshots} />
    </div>
  );
}
