import {
  getHoldingTickers,
  getLatestAlertsRun,
  getLatestDiscoveries,
  getNewsForHoldings,
  getRecentAlerts,
} from "@/lib/queries";
import DiscoveriesFeed from "../components/discoveries-feed";
import AlertsList from "../components/alerts-list";
import NewsStream from "../components/news-stream";
import Link from "next/link";
import { ChevronLeft } from "lucide-react";

export const revalidate = 300;

export default async function InsightsPage() {
  const [discoveries, activeAlerts, latestAlertsRun, holdingTickers] = await Promise.all([
    getLatestDiscoveries(),
    getRecentAlerts(20),
    getLatestAlertsRun(),
    getHoldingTickers(),
  ]);

  const news = await getNewsForHoldings(holdingTickers, 40);

  return (
    <div className="space-y-4 sm:space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link
            href="/"
            className="inline-flex items-center justify-center w-8 h-8 rounded-lg text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
            aria-label="Back to Investments"
          >
            <ChevronLeft size={20} strokeWidth={2} />
          </Link>
          <h1 className="text-lg sm:text-xl font-semibold text-gray-900 dark:text-gray-50">Insights</h1>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6">
        <DiscoveriesFeed runTime={discoveries.run_time} items={discoveries.items} />
        <AlertsList active={activeAlerts} latestRun={latestAlertsRun} />
      </div>

      <NewsStream items={news} />
    </div>
  );
}
