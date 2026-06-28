import { ShoppingCart } from "lucide-react";

export const metadata = { title: "Spending" };

export default function SpendingPage() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[50vh] gap-3 text-center">
      <div className="w-12 h-12 rounded-full bg-gray-100 dark:bg-gray-800 flex items-center justify-center">
        <ShoppingCart size={24} className="text-gray-400" strokeWidth={1.5} />
      </div>
      <h1 className="text-lg font-semibold text-gray-900 dark:text-gray-50">Spending</h1>
      <p className="text-sm text-gray-400 max-w-xs">
        Category breakdown and spending trends coming in Phase 22.
      </p>
    </div>
  );
}
