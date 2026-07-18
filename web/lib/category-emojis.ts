export const CATEGORY_EMOJIS: Record<string, string> = {
  "Eating out":    "🍽️",
  "Groceries":     "🛒",
  "Entertainment": "🎬",
  "Shopping":      "🛍️",
  "Transport":     "🚇",
  "Bills":         "💡",
  "General":       "📦",
  "Savings":       "💰",
  "Transfers":     "🔄",
  "Cash":          "💵",
  "Finances":      "📊",
  "Family":        "👨‍👩‍👧",
  "Personal care": "💆",
  "Health":        "❤️‍🩹",
  "Education":     "📚",
  "Holidays":      "✈️",
  "Mortgage":      "🏠",
  "Home":          "🏡",
  "Subscription":  "🔔",
  "Cats":          "🐱",
  "Car":           "🚗",
};

export const CATEGORY_COLORS: Record<string, string> = {
  "Eating out":    "#f97316",
  "Groceries":     "#22c55e",
  "Entertainment": "#a855f7",
  "Shopping":      "#ec4899",
  "Transport":     "#3b82f6",
  "Bills":         "#64748b",
  "General":       "#94a3b8",
  "Savings":       "#10b981",
  "Transfers":     "#6b7280",
  "Cash":          "#eab308",
  "Finances":      "#8b5cf6",
  "Family":        "#f43f5e",
  "Personal care": "#14b8a6",
  "Health":        "#ef4444",
  "Education":     "#0ea5e9",
  "Holidays":      "#f59e0b",
  "Mortgage":      "#1d4ed8",
  "Home":          "#16a34a",
  "Subscription":  "#7c3aed",
  // Was #f97316, which collided with "Eating out" — both are active categories
  // and now always render side by side, so Cats gets its own hue.
  "Cats":          "#06b6d4",
  "Car":           "#b45309",
};

export function getCategoryEmoji(category: string | null | undefined): string {
  if (!category) return "📦";
  return CATEGORY_EMOJIS[category] ?? "📦";
}

export function getCategoryColor(category: string | null | undefined): string {
  if (!category) return "#94a3b8";
  return CATEGORY_COLORS[category] ?? "#94a3b8";
}

// Blends a hex color toward white — used to show "previous year" as a lighter
// tint of the same category color, with "current year" left at full saturation.
export function lightenColor(hex: string, amount: number): string {
  const n = parseInt(hex.slice(1), 16);
  const channel = (shift: number) => {
    const c = (n >> shift) & 255;
    return Math.round(c + (255 - c) * amount);
  };
  return `#${[16, 8, 0].map(shift => channel(shift).toString(16).padStart(2, "0")).join("")}`;
}
