"use client";

import { useState } from "react";
import Link from "next/link";
import { Receipt } from "lucide-react";
import { type SpendingData } from "@/lib/queries";
import CategoryChart from "./category-chart";
import SpendingChart from "./spending-chart";
import SpendingInsights, { ThisMonthHero } from "./spending-insights";

type Account = "all" | "personal" | "joint";

const BUDGETS: Record<Account, number> = { all: 5800, personal: 800, joint: 5200 };

type Props = { data: SpendingData };

export default function SpendingClient({ data }: Props) {
  const [account, setAccount] = useState<Account>("joint");
  const d = data[account];

  return (
    <div className="flex flex-col gap-5">
      {/* Account toggle + All transactions */}
      <div className="flex items-center justify-between">
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
        <Link
          href="/transactions"
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
        >
          <Receipt size={13} strokeWidth={2} />
          All transactions
        </Link>
      </div>

      <ThisMonthHero monthly={d.monthly} daily={d.daily} budget={BUDGETS[account]} recurring={d.recurring} />
      <CategoryChart key={`cat-${account}`} byCategory={d.byCategory} />
      <SpendingChart key={`spend-${account}`} monthly={d.monthly} weekly={d.weekly} daily={d.daily} />
      <SpendingInsights topMerchants={d.topMerchants} byDayOfWeek={d.byDayOfWeek} />
    </div>
  );
}
