"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { BarChart3, Layers3, Menu, Sparkles, Target, Workflow, X } from "lucide-react";
import { ApiStatus } from "./ApiStatus";
import { ThemeToggle } from "./ThemeToggle";

const NAV = [
  { href: "/prospects", label: "Prospects", icon: Target },
  { href: "/campaigns", label: "Campaigns", icon: Layers3 },
  { href: "/discover", label: "Discover", icon: Sparkles },
  { href: "/runs", label: "Workflow runs", icon: Workflow },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
];

function isActive(pathname: string, href: string) {
  return pathname === href || pathname.startsWith(`${href}/`);
}

function Brand() {
  return (
    <Link aria-label="Airflow Sales" className="brand-link" href="/prospects">
      <span className="brand-mark">
        <span />
      </span>
      <span className="brand-name">
        airflow <b>sales</b>
      </span>
    </Link>
  );
}

function NavItems({ pathname, onNavigate }: { pathname: string; onNavigate?: () => void }) {
  return (
    <>
      {NAV.map(({ href, label, icon: Icon }) => {
        const active = isActive(pathname, href);
        return (
          <Link
            aria-current={active ? "page" : undefined}
            className={`nav-item${active ? " active" : ""}`}
            href={href}
            key={href}
            onClick={onNavigate}
          >
            <Icon />
            <span>{label}</span>
          </Link>
        );
      })}
    </>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const current = NAV.find((item) => isActive(pathname, item.href));
  const title = current?.label ?? "Not found";

  // Route changes always close the mobile menu.
  useEffect(() => {
    setMenuOpen(false);
  }, [pathname]);

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>

      <aside className="sidebar">
        <div className="brand-row">
          <Brand />
        </div>

        <nav aria-label="Main navigation" className="main-nav">
          <NavItems pathname={pathname} />
        </nav>
      </aside>

      <div className="main-content">
        <div className="mobile-bar">
          <Brand />
          <button
            aria-expanded={menuOpen}
            aria-label={menuOpen ? "Close menu" : "Open menu"}
            className="icon-button"
            onClick={() => setMenuOpen((open) => !open)}
            type="button"
          >
            {menuOpen ? <X /> : <Menu />}
          </button>
        </div>

        {menuOpen ? (
          <nav aria-label="Mobile navigation" className="mobile-nav">
            <NavItems pathname={pathname} onNavigate={() => setMenuOpen(false)} />
          </nav>
        ) : null}

        <header className="topbar">
          <span className="top-title">{title}</span>
          <div className="top-actions">
            <ApiStatus />
            <ThemeToggle />
          </div>
        </header>

        <main className="content-wrap" id="main-content" tabIndex={-1}>
          {children}
        </main>
      </div>
    </div>
  );
}
