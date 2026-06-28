"use client";

import { useState } from "react";
import { type SpendingData } from "@/lib/queries";
import CategoryChart from "./category-chart";
import SpendingChart from "./spending-chart";
import SpendingInsights, { ThisMonthHero } from "./spending-insights";

type Account = "all" | "personal" | "joint";

type Props = { data: SpendingData };

export default function SpendingClient({ data }: Props) {
  const [account, setAccount] = useState<Account>("joint");
  const d = data[account];

  return (
    <div className="flex flex-col gap-5">
      {/* Account toggle */}
      <div className="flex items-center gap-0.5 bg-gray-100 dark:bg-gray-800 rounded-md p-0.5 w-fit">
        {(["all", "personal", "joint"] as const).map((a) => (
          <button
            key={a}
            onClick={() => setAccount(a)}
            className={`px-2.5 py-1 text-xs font-medium rounded transition-colors ${
              account === a
                ? "bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-50 shadow-sm"
                : "text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-50"
            }`}
          >
            {a === "all" ? "All" : a === "personal" ? "Personal" : "Joint"}
          </button>
        ))}
      </div>

      <ThisMonthHero monthly={d.monthly} daily={d.daily} />
      <CategoryChart key={`cat-${account}`} byCategory={d.byCategory} />
      <SpendingChart key={`spend-${account}`} monthly={d.monthly} weekly={d.weekly} daily={d.daily} />
      <SpendingInsights topMerchants={d.topMerchants} byDayOfWeek={d.byDayOfWeek} />
    </div>
  );
}
