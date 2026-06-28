"use client";

import { useState } from "react";
import { type SpendingData } from "@/lib/queries";
import CategoryChart from "./category-chart";
import SpendingChart from "./spending-chart";
import SpendingInsights from "./spending-insights";

type Account = "all" | "personal" | "joint";

type Props = { data: SpendingData };

export default function SpendingClient({ data }: Props) {
  const [account, setAccount] = useState<Account>("all");
  const d = data[account];

  return (
    <div className="flex flex-col gap-5">
      {/* Account toggle */}
      <div className="flex rounded-lg border border-gray-200 dark:border-gray-800 overflow-hidden w-fit text-sm">
        {(["all", "personal", "joint"] as const).map((a) => (
          <button
            key={a}
            onClick={() => setAccount(a)}
            className={`px-4 py-1.5 font-medium capitalize transition-colors ${
              account === a
                ? "bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900"
                : "text-gray-500 hover:bg-gray-50 dark:hover:bg-gray-900"
            }`}
          >
            {a === "all" ? "All" : a === "personal" ? "Personal" : "Joint"}
          </button>
        ))}
      </div>

      <CategoryChart byCategory={d.byCategory} />
      <SpendingChart monthly={d.monthly} weekly={d.weekly} />
      <SpendingInsights monthly={d.monthly} topMerchants={d.topMerchants} byDayOfWeek={d.byDayOfWeek} />
    </div>
  );
}
