"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { AlertsBell } from "@/app/components/alerts-bell";
import { API_URL } from "@/lib/api";
import { useLiveConnected } from "@/lib/events";

const NAV_SECTIONS: { title: string; links: { href: string; label: string }[] }[] = [
  {
    title: "Аналитика",
    links: [
      { href: "/", label: "Дашборд" },
      { href: "/#searches", label: "Поиски" },
      { href: "/our-listings", label: "Наши объявления" },
    ],
  },
  {
    title: "Настройки",
    links: [
      { href: "/#accounts", label: "Аккаунты" },
      { href: "/#proxies", label: "Прокси" },
      { href: "/#alerts", label: "Алерты" },
    ],
  },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const live = useLiveConnected();

  const navLinkClass = (href: string) => {
    const base = href.split("#")[0];
    const active = base === "/" ? pathname === "/" : pathname.startsWith(base);
    return `block rounded-lg px-3 py-2 text-sm transition ${
      active && !href.includes("#")
        ? "bg-neutral-800 text-neutral-100"
        : "text-neutral-400 hover:bg-neutral-900 hover:text-neutral-200"
    }`;
  };

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[224px_1fr]">
      <aside className="sticky top-0 hidden h-screen flex-col border-r border-neutral-800/80 bg-neutral-950/95 px-3 py-4 lg:flex">
        <Link href="/" className="mb-4 flex items-center gap-2 px-2 text-sm font-semibold">
          <span className="inline-block h-2 w-2 rounded-full bg-emerald-400" />
          avito-toolkit
        </Link>
        <nav className="flex flex-1 flex-col gap-4">
          {NAV_SECTIONS.map((section) => (
            <div key={section.title}>
              <p className="px-3 pb-1 text-[10px] uppercase tracking-wider text-neutral-600">
                {section.title}
              </p>
              {section.links.map((link) => (
                <Link key={link.href} href={link.href} className={navLinkClass(link.href)}>
                  {link.label}
                </Link>
              ))}
            </div>
          ))}
        </nav>
        <a
          href={`${API_URL}/docs`}
          target="_blank"
          rel="noreferrer"
          className="rounded-lg px-3 py-2 text-xs text-neutral-500 transition hover:bg-neutral-900 hover:text-neutral-200"
        >
          API-документация ↗
        </a>
      </aside>

      <div className="flex min-h-screen flex-col">
        <header className="sticky top-0 z-20 border-b border-neutral-800/80 bg-neutral-950/85 backdrop-blur">
          <div className="flex items-center justify-between gap-3 px-4 py-2.5 sm:px-6">
            <div className="flex items-center gap-3">
              <Link href="/" className="flex items-center gap-2 text-sm font-semibold lg:hidden">
                <span className="inline-block h-2 w-2 rounded-full bg-emerald-400" />
                avito-toolkit
              </Link>
              <button
                type="button"
                onClick={() => setMenuOpen((value) => !value)}
                className="rounded-lg border border-neutral-800 px-3 py-1.5 text-xs text-neutral-300 lg:hidden"
              >
                {menuOpen ? "Закрыть" : "Меню"}
              </button>
            </div>
            <div className="flex items-center gap-2">
              <span
                className={`flex items-center gap-1.5 text-[11px] ${
                  live ? "text-emerald-300/90" : "text-neutral-500"
                }`}
                title={live ? "Обновления в реальном времени" : "Переподключение к событиям…"}
              >
                <span
                  className={`inline-block h-1.5 w-1.5 rounded-full ${
                    live ? "bg-emerald-400" : "bg-neutral-600"
                  }`}
                />
                {live ? "live" : "офлайн"}
              </span>
              <AlertsBell />
            </div>
          </div>
          {menuOpen ? (
            <nav className="flex flex-col gap-1 border-t border-neutral-800 px-3 py-2">
              {NAV_SECTIONS.flatMap((section) => section.links).map((link) => (
                <Link
                  key={link.href}
                  href={link.href}
                  onClick={() => setMenuOpen(false)}
                  className={navLinkClass(link.href)}
                >
                  {link.label}
                </Link>
              ))}
            </nav>
          ) : null}
        </header>

        <div className="flex-1">{children}</div>
        <footer className="border-t border-neutral-900 px-4 py-5 text-xs text-neutral-600 sm:px-6">
          avito-toolkit · аналитика рынка, конкуренты и рекомендации по ценам
        </footer>
      </div>
    </div>
  );
}
