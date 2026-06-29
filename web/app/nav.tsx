"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LineChart, PiggyBank, TrendingUp, Landmark, Home, Menu, X, Receipt, LayoutDashboard, ShoppingCart, type LucideIcon } from "lucide-react";
import SyncButton from "./components/sync-button";
import { useState, useRef, useEffect } from "react";

type Tab = {
  label: string;
  shortLabel?: string; // used in the mobile bottom tab bar, falls back to label
  href: string;
  icon: LucideIcon;
  activeColor: string; // Tailwind text colour class for active state
};

const tabs: Tab[] = [
  { label: "Investments", shortLabel: "Invest", href: "/",          icon: LineChart,    activeColor: "text-blue-600 dark:text-blue-400"     },
  { label: "Savings",     href: "/savings",           icon: PiggyBank,    activeColor: "text-emerald-500 dark:text-emerald-400" },
  { label: "Pensions",    href: "/pensions",          icon: Landmark,     activeColor: "text-amber-500 dark:text-amber-400"   },
  { label: "House",       href: "/mortgage",          icon: Home,         activeColor: "text-orange-500 dark:text-orange-400" },
  { label: "Net Worth",   href: "/net-worth",         icon: TrendingUp,   activeColor: "text-violet-500 dark:text-violet-400" },
  { label: "Spending",    shortLabel: "Spent", href: "/spending",    icon: ShoppingCart, activeColor: "text-rose-500 dark:text-rose-400"     },
];

const menuLinks = [
  { label: "Transactions", href: "/transactions", icon: Receipt },
  { label: "Budgets",      href: "/budgets",      icon: LayoutDashboard },
];

// Longest matching prefix wins, so /mortgage/insights activates Insights, not House.
function activeHref(pathname: string): string {
  let best = "";
  for (const { href } of tabs) {
    const match =
      href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
    if (match && href.length > best.length) best = href;
  }
  return best;
}

function BurgerMenu() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const pathname = usePathname();

  // Close on outside click
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    if (open) document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  // Close on route change
  useEffect(() => { setOpen(false); }, [pathname]);

  const isMenuActive = menuLinks.some(
    ({ href }) => pathname === href || pathname.startsWith(`${href}/`)
  );

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-label="Open menu"
        className={`inline-flex items-center justify-center w-8 h-8 rounded-md transition-colors ${
          isMenuActive || open
            ? "bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-gray-50"
            : "text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-50 hover:bg-gray-50 dark:hover:bg-gray-900"
        }`}
      >
        {open ? <X size={18} strokeWidth={2} /> : <Menu size={18} strokeWidth={2} />}
      </button>
      {open && (
        <div className="absolute right-0 top-full mt-1 w-44 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-950 shadow-lg py-1 z-50">
          {menuLinks.map(({ label, href, icon: Icon }) => {
            const active = pathname === href || pathname.startsWith(`${href}/`);
            return (
              <Link
                key={href}
                href={href}
                className={`flex items-center gap-2.5 px-3 py-2 text-sm font-medium transition-colors ${
                  active
                    ? "bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-gray-50"
                    : "text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-50 hover:bg-gray-50 dark:hover:bg-gray-900"
                }`}
              >
                <Icon size={15} strokeWidth={2} aria-hidden="true" />
                {label}
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function Nav() {
  const pathname = usePathname();
  if (pathname === "/login") return null;
  const current = activeHref(pathname);

  return (
    <>
      {/* Desktop top nav */}
      <header className="hidden sm:block sticky top-0 z-40 border-b border-gray-200 dark:border-gray-800 bg-white/80 dark:bg-gray-950/80 backdrop-blur">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex h-14 items-center gap-4">
            <Link href="/" className="flex items-center gap-2 shrink-0">
              <span className="inline-flex items-center justify-center w-7 h-7 rounded-lg bg-gradient-to-br from-blue-600 to-indigo-600 text-white shadow-sm">
                <svg viewBox="0 0 24 24" className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M3 17l6-6 4 4 8-8" />
                  <path d="M14 7h7v7" />
                </svg>
              </span>
              <span className="font-semibold tracking-tight text-gray-900 dark:text-gray-50">
                Fin Assist
              </span>
            </Link>
            <SyncButton />
            <nav className="flex items-center gap-1 ml-auto">
              {tabs.map(({ label, href, icon: Icon, activeColor }) => {
                const active = href === current;
                return (
                  <Link
                    key={href}
                    href={href}
                    className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                      active
                        ? `bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-gray-50`
                        : "text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-50 hover:bg-gray-50 dark:hover:bg-gray-900"
                    }`}
                  >
                    <Icon
                      size={16}
                      strokeWidth={2}
                      aria-hidden="true"
                      className={active ? activeColor : ""}
                    />
                    {label}
                  </Link>
                );
              })}
            </nav>
            <BurgerMenu />
          </div>
        </div>
      </header>

      {/* Mobile top bar */}
      <header className="sm:hidden sticky top-0 z-40 border-b border-gray-200 dark:border-gray-800 bg-white/90 dark:bg-gray-950/90 backdrop-blur">
        <div className="px-4 h-12 flex items-center gap-2">
          <span className="inline-flex items-center justify-center w-6 h-6 rounded-md bg-gradient-to-br from-blue-600 to-indigo-600 text-white shadow-sm">
            <svg viewBox="0 0 24 24" className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 17l6-6 4 4 8-8" />
              <path d="M14 7h7v7" />
            </svg>
          </span>
          <span className="font-semibold tracking-tight text-gray-900 dark:text-gray-50">
            Fin Assist
          </span>
          <div className="ml-auto flex items-center gap-2">
            <SyncButton />
            <BurgerMenu />
          </div>
        </div>
      </header>

      {/* Mobile bottom tab bar */}
      <nav
        className="sm:hidden fixed bottom-0 inset-x-0 z-40 border-t border-gray-200 dark:border-gray-800 bg-white/95 dark:bg-gray-950/95 backdrop-blur pb-[env(safe-area-inset-bottom)]"
        aria-label="Primary"
      >
        <div className="flex h-16">
          {tabs.map(({ label, shortLabel, href, icon: Icon, activeColor }) => {
            const active = href === current;
            return (
              <Link
                key={href}
                href={href}
                className={`flex-1 flex flex-col items-center justify-center gap-1 text-[11px] font-medium transition-colors ${
                  active ? activeColor : "text-gray-400 dark:text-gray-500"
                }`}
              >
                <Icon
                  size={22}
                  strokeWidth={active ? 2.25 : 1.75}
                  aria-hidden="true"
                />
                <span>{shortLabel ?? label}</span>
              </Link>
            );
          })}
        </div>
      </nav>
    </>
  );
}
