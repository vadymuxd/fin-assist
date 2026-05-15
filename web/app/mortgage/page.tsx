import { computeMortgageDeltas, getMortgageSnapshots } from "@/lib/queries";
import MortgageKpiCards from "./components/mortgage-kpi-cards";
import MortgageChart from "./components/mortgage-chart";
import MortgageMetrics from "./components/mortgage-metrics";
import Link from "next/link";
import { Lightbulb } from "lucide-react";

export const revalidate = 300;

export default async function MortgagePage() {
  const snapshots = await getMortgageSnapshots().catch(() => []);
  const deltas = computeMortgageDeltas(snapshots);

  return (
    <div className="space-y-4 sm:space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg sm:text-xl font-semibold text-gray-900 dark:text-gray-50">Mortgage</h1>
        <div className="flex items-center gap-3">
          {deltas && (
            <span className="text-xs text-gray-500 dark:text-gray-400">
              Updated {new Date(deltas.latest.updated_at).toLocaleDateString("en-GB", {
                day: "2-digit",
                month: "short",
                year: "numeric",
              })}
            </span>
          )}
          <Link
            href="/mortgage/insights"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
          >
            <Lightbulb size={13} strokeWidth={2} />
            Insights
          </Link>
        </div>
      </div>
      <MortgageKpiCards deltas={deltas} />
      <MortgageChart snapshots={snapshots} />
      <MortgageMetrics snapshots={snapshots} />
    </div>
  );
}
