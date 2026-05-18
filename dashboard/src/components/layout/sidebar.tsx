"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutDashboard,
  BarChart3,
  Zap,
  ArrowLeftRight,
  Target,
  FlaskConical,
  Settings,
  LogOut,
} from "lucide-react";

const NAV_ITEMS = [
  { href: "/",          label: "Overview",    icon: LayoutDashboard },
  { href: "/markets",   label: "Markets",     icon: BarChart3 },
  { href: "/surges",    label: "Surges",      icon: Zap },
  { href: "/trades",    label: "Trades",      icon: ArrowLeftRight },
  { href: "/positions", label: "Positions",   icon: Target },
  { href: "/backtest",  label: "Backtest",    icon: FlaskConical },
  { href: "/settings",  label: "Settings",    icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();

  async function handleLogout() {
    await fetch("/api/auth/logout", { method: "POST" });
    router.push("/login");
  }

  return (
    <>
      {/* Desktop sidebar */}
      <aside className="hidden lg:flex flex-col w-[220px] min-w-[220px] h-screen sticky top-0 bg-raised border-r border-border-glass">
        <div className="px-4 py-5 flex items-center gap-2">
          <span className="text-lg font-bold text-text-primary">Scalper</span>
          <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-accent-primary/20 text-accent-primary">
            PAPER
          </span>
        </div>
        <nav className="flex-1 overflow-y-auto px-2 space-y-0.5">
          {NAV_ITEMS.map((item) => {
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors ${
                  active
                    ? "bg-tone-cyan text-accent-primary font-medium border-l-[3px] border-accent-primary"
                    : "text-text-secondary hover:text-text-primary hover:bg-surface"
                }`}
              >
                <item.icon className="w-4 h-4 shrink-0" />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
        <button
          onClick={handleLogout}
          className="flex items-center gap-3 px-5 py-3 text-sm text-text-secondary hover:text-status-loss transition-colors border-t border-border-glass"
        >
          <LogOut className="w-4 h-4 shrink-0" />
          <span>Logout</span>
        </button>
      </aside>

      {/* Tablet: icon-only sidebar */}
      <aside className="hidden md:flex lg:hidden flex-col w-14 min-w-14 h-screen sticky top-0 bg-raised border-r border-border-glass items-center py-4">
        <div className="mb-4 text-xs font-bold text-accent-primary">PM</div>
        <nav className="flex-1 overflow-y-auto space-y-1">
          {NAV_ITEMS.map((item) => {
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                title={item.label}
                className={`flex items-center justify-center w-10 h-10 rounded-md transition-colors ${
                  active
                    ? "bg-tone-cyan text-accent-primary"
                    : "text-text-secondary hover:text-text-primary hover:bg-surface"
                }`}
              >
                <item.icon className="w-4 h-4" />
              </Link>
            );
          })}
        </nav>
      </aside>

      {/* Mobile bottom nav */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 z-50 bg-raised border-t border-border-glass flex justify-around py-1 px-1">
        {NAV_ITEMS.slice(0, 5).map((item) => {
          const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex flex-col items-center justify-center gap-0.5 min-h-12 min-w-12 text-xs ${
                active ? "text-accent-primary" : "text-text-secondary"
              }`}
            >
              <item.icon className="w-5 h-5" />
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>
    </>
  );
}
