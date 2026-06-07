import { getMortgageInsights } from "@/lib/queries";
import InsightCard from "./components/insight-card";
import GetInsightsButton from "./components/get-insights-button";
import Link from "next/link";
import { ArrowLeft, Lightbulb } from "lucide-react";

export const revalidate = 60;

export const metadata = { title: "Insights" };

export default async function MortgageInsightsPage() {
  const insights = await getMortgageInsights().catch(() => []);

  return (
    <div className="space-y-4 sm:space-y-6">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <Link
            href="/mortgage"
            className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          >
            <ArrowLeft size={13} strokeWidth={2} />
            House
          </Link>
          <h1 className="text-lg sm:text-xl font-semibold text-gray-900 dark:text-gray-50">
            Insights
          </h1>
        </div>
        <GetInsightsButton />
      </div>

      <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400 max-w-2xl">
        Weekly UK mortgage-market monitor — BoE market-average 2yr/5yr fixed rates at ~85% LTV with
        a week-over-week comparison, the Bank of England base rate and MPC schedule, and a
        recommended action grounded in your remortgage.
        Reports generate automatically each Sunday; press <span className="font-medium">Get
        Insights</span> to run one now (it appears here in a minute or two).
      </p>

      {insights.length === 0 ? (
        <div className="rounded-xl border border-dashed border-gray-300 dark:border-gray-700 px-6 py-14 text-center">
          <div className="inline-flex items-center justify-center w-11 h-11 rounded-full bg-blue-100 dark:bg-blue-500/15 text-blue-600 dark:text-blue-400 mb-3">
            <Lightbulb size={20} strokeWidth={2} />
          </div>
          <div className="text-sm font-medium text-gray-900 dark:text-gray-50">
            No insights yet
          </div>
          <div className="text-xs text-gray-500 dark:text-gray-400 mt-1 max-w-sm mx-auto">
            Press “Get Insights” above to run the mortgage-market monitor. The first report will
            appear here once it finishes.
          </div>
        </div>
      ) : (
        <div className="space-y-3 sm:space-y-4">
          {insights.map((insight, idx) => (
            <InsightCard key={insight.id} insight={insight} open={idx === 0} />
          ))}
        </div>
      )}
    </div>
  );
}
