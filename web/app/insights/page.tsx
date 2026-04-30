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
import { ArrowLeft } from "lucide-react";

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
            className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          >
            <ArrowLeft size={13} strokeWidth={2} />
            Investments
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
