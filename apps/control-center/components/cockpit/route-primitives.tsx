"use client";

import type { ReactNode } from "react";
import { useLocale } from "@/lib/i18n";

export function LocaleSwitcher() {
  const { locale, setLocale, t } = useLocale();
  return <div className="locale-switcher" role="group" aria-label={t.languageSwitcher}><button type="button" onClick={() => setLocale("th")} aria-pressed={locale === "th"}>{t.thai}</button><span>|</span><button type="button" onClick={() => setLocale("en")} aria-pressed={locale === "en"}>{t.english}</button></div>;
}

export function RouteHeader({ route }: Readonly<{ route: "projects" | "approvals" | "evidence" }>) {
  const { t } = useLocale();
  return <header className="cockpit-header cockpit-route-header"><div><p className="cockpit-overline">{t.v02.demo}</p><h1>{t.v02.route[route].title}</h1><p className="route-description">{t.v02.route[route].description}</p></div><LocaleSwitcher /></header>;
}

export function StatusBadge({ tone, children }: Readonly<{ tone: string; children: ReactNode }>) {
  return <span className={`cockpit-badge cockpit-badge--${tone}`}>{children}</span>;
}

export function FilterControl<T extends string>({ value, onChange, options, label }: Readonly<{ value: T; onChange: (value: T) => void; options: readonly { value: T; label: string }[]; label: string }>) {
  return <div className="filter-control" role="group" aria-label={label}>{options.map((option) => <button type="button" key={option.value} className={value === option.value ? "is-selected" : ""} aria-pressed={value === option.value} onClick={() => onChange(option.value)}>{option.label}</button>)}</div>;
}

export function DetailPanel({ title, children, onClose }: Readonly<{ title: string; children: ReactNode; onClose: () => void }>) {
  const { t } = useLocale();
  return <aside className="detail-panel" aria-label={title}><div className="detail-panel__head"><h2>{title}</h2><button type="button" onClick={onClose}>{t.v02.actions.closePanel}</button></div>{children}</aside>;
}

export function LocalToast({ message, onClose }: Readonly<{ message: string | null; onClose: () => void }>) {
  const { t } = useLocale();
  if (!message) return null;
  return <div className="cockpit-toast" role="status"><p>{message}</p><button type="button" onClick={onClose}>{t.close}</button></div>;
}
