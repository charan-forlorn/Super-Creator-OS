"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { LocaleProvider, useLocale } from "@/lib/i18n";

type NavigationItem = { id: "today" | "projects" | "agents" | "workflows" | "evidence" | "approvals" | "activity" | "settings"; href?: string };

const navigation: readonly NavigationItem[] = [
  { id: "today", href: "/" },
  { id: "projects", href: "/projects" },
  { id: "agents" },
  { id: "workflows" },
  { id: "evidence", href: "/evidence" },
  { id: "approvals", href: "/approvals" },
  { id: "activity" },
  { id: "settings" },
];

const fireflies = [
  "cockpit-firefly--1",
  "cockpit-firefly--2",
  "cockpit-firefly--3",
  "cockpit-firefly--4",
  "cockpit-firefly--5",
  "cockpit-firefly--6",
  "cockpit-firefly--7",
  "cockpit-firefly--8",
  "cockpit-firefly--9",
  "cockpit-firefly--10",
] as const;

function CockpitShellSurface({ children }: Readonly<{ children: ReactNode }>) {
  const { t } = useLocale();
  const pathname = usePathname();
  const ambientMode = pathname === "/" ? "full" : "minimal";

  return (
    <main className={`cockpit-shell cockpit-shell--ambient-${ambientMode}`}>
      <div className="cockpit-ambient" aria-hidden="true">
        {fireflies.map((className) => <span className={`cockpit-firefly ${className}`} key={className} />)}
      </div>
      <aside className="cockpit-sidebar" aria-label={t.productName}>
        <div className="cockpit-brand"><span className="cockpit-brand__mark">S</span><span>{t.appName}</span></div>
        <nav className="cockpit-nav" aria-label={t.productName}>
          {navigation.map((item, index) => item.href ? (
            <Link className={pathname === item.href ? "cockpit-nav__item is-active" : "cockpit-nav__item"} href={item.href} key={item.id} aria-current={pathname === item.href ? "page" : undefined}>
              <span className="cockpit-nav__glyph">{index + 1}</span>{t.nav[item.id]}
            </Link>
          ) : <button type="button" className="cockpit-nav__item is-unavailable" key={item.id} aria-disabled="true" disabled><span className="cockpit-nav__glyph">{index + 1}</span>{t.nav[item.id]}</button>)}
        </nav>
        <div className="cockpit-sidebar__footer"><span className="local-state"><i />{t.localFirst}</span><strong>{t.workspace}</strong></div>
      </aside>
      {children}
    </main>
  );
}

export function CockpitShell({ children }: Readonly<{ children: ReactNode }>) {
  return <LocaleProvider><CockpitShellSurface>{children}</CockpitShellSurface></LocaleProvider>;
}
