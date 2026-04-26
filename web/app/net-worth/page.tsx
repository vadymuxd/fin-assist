import { getNetWorthData } from "@/lib/queries";
import NetWorthKpiCards from "./components/net-worth-kpi-cards";
import NetWorthChart from "./components/net-worth-chart";
import NetWorthAllocationChart from "./components/net-worth-allocation-chart";

export const revalidate = 300;

export default async function NetWorthPage() {
  const data = await getNetWorthData().catch(() => [] as Awaited<ReturnType<typeof getNetWorthData>>);
  const latest = data.length > 0 ? data[data.length - 1] : null;

  return (
    <div className="space-y-4 sm:space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg sm:text-xl font-semibold text-gray-900 dark:text-gray-50">Net Worth</h1>
        {latest && (
          <span className="text-xs text-gray-500 dark:text-gray-400">
            Updated {new Date(`${latest.date}T00:00:00Z`).toLocaleDateString("en-GB", {
              month: "short",
              year: "numeric",
              timeZone: "UTC",
            })}
          </span>
        )}
      </div>
      <NetWorthKpiCards data={data} />
      <NetWorthChart data={data} />
      <NetWorthAllocationChart data={data} />
    </div>
  );
}
