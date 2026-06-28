import { LayoutDashboard } from "lucide-react";

export const metadata = { title: "Budgets" };

export default function BudgetsPage() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[50vh] gap-3 text-center">
      <div className="w-12 h-12 rounded-full bg-gray-100 dark:bg-gray-800 flex items-center justify-center">
        <LayoutDashboard size={24} className="text-gray-400" strokeWidth={1.5} />
      </div>
      <h1 className="text-lg font-semibold text-gray-900 dark:text-gray-50">Budgets</h1>
      <p className="text-sm text-gray-400 max-w-xs">
        Budget rules and category breakdowns coming in Phase 21.
      </p>
    </div>
  );
}
