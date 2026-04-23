"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

type Tab = {
  label: string;
  href: string;
  icon: (active: boolean) => React.ReactNode;
};

const tabs: Tab[] = [
  {
    label: "Dashboard",
    href: "/",
    icon: (active) => (
      <svg
        className="w-6 h-6"
        fill={active ? "currentColor" : "none"}
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth={1.8}
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M3 13h8V3H3v10zm10 8h8V11h-8v10zM3 21h8v-6H3v6zm10-18v6h8V3h-8z"
        />
      </svg>
    ),
  },
  {
    label: "Insights",
    href: "/insights",
    icon: (active) => (
      <svg
        className="w-6 h-6"
        fill={active ? "currentColor" : "none"}
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth={1.8}
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M11 4a7 7 0 104.95 11.95l3.55 3.55 1.4-1.4-3.55-3.55A7 7 0 0011 4zm0 2a5 5 0 110 10 5 5 0 010-10z"
        />
      </svg>
    ),
  },
];

function isActive(href: string, pathname: string) {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}

export default function Nav() {
  const pathname = usePathname();

  return (
    <>
      {/* Desktop top nav */}
      <header className="hidden sm:block sticky top-0 z-40 border-b border-gray-200 dark:border-gray-800 bg-white/80 dark:bg-gray-950/80 backdrop-blur">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex h-14 items-center justify-between gap-4">
            <span className="font-semibold tracking-tight text-gray-900 dark:text-gray-50">
              Fin Assist
            </span>
            <nav className="flex items-center gap-1">
              {tabs.map(({ label, href }) => {
                const active = isActive(href, pathname);
                return (
                  <Link
                    key={href}
                    href={href}
                    className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                      active
                        ? "bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-gray-50"
                        : "text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-50 hover:bg-gray-50 dark:hover:bg-gray-900"
                    }`}
                  >
                    {label}
                  </Link>
                );
              })}
            </nav>
          </div>
        </div>
      </header>

      {/* Mobile top bar — just the logo */}
      <header className="sm:hidden sticky top-0 z-40 border-b border-gray-200 dark:border-gray-800 bg-white/90 dark:bg-gray-950/90 backdrop-blur">
        <div className="px-4 h-12 flex items-center">
          <span className="font-semibold tracking-tight text-gray-900 dark:text-gray-50">
            Fin Assist
          </span>
        </div>
      </header>

      {/* Mobile bottom tab bar */}
      <nav
        className="sm:hidden fixed bottom-0 inset-x-0 z-40 border-t border-gray-200 dark:border-gray-800 bg-white/95 dark:bg-gray-950/95 backdrop-blur pb-[env(safe-area-inset-bottom)]"
        aria-label="Primary"
      >
        <div className="flex h-16">
          {tabs.map(({ label, href, icon }) => {
            const active = isActive(href, pathname);
            return (
              <Link
                key={href}
                href={href}
                className={`flex-1 flex flex-col items-center justify-center gap-1 text-[11px] font-medium transition-colors ${
                  active
                    ? "text-gray-900 dark:text-gray-50"
                    : "text-gray-400 dark:text-gray-500"
                }`}
              >
                {icon(active)}
                <span>{label}</span>
              </Link>
            );
          })}
        </div>
      </nav>
    </>
  );
}
