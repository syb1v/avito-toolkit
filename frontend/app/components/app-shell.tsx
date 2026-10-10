"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense } from "react";
import { useState } from "react";

import { AlertsBell } from "@/app/components/alerts-bell";
import { ChatButton } from "@/app/components/chat-panel";
import { Icon } from "@/app/components/nav-icon";
import { SellerSwitcher } from "@/app/components/seller-switcher";
import { API_URL } from "@/lib/api";
import { useLiveConnected } from "@/lib/events";

type NavLink = { href: string; label: string; icon: Parameters<typeof Icon>[0]["name"] };

const NAV_SECTIONS: { title: string; links: NavLink[] }[] = [
  {
    title: "Работа",
    links: [
      { href: "/", label: "Обзор", icon: "overview" as const },
      { href: "/searches", label: "Поиски", icon: "searches" as const },
      { href: "/our-listings", label: "Мои объявления", icon: "listings" as const },
      { href: "/recommendations", label: "Рекомендации", icon: "recommendations" as const },
      { href: "/agents", label: "Агенты", icon: "agents" as const },
      { href: "/chat", label: "Чат", icon: "chat" as const },
    ],
  },
  {
    title: "Система",
    links: [
      { href: "/accounts", label: "Аккаунты", icon: "accounts" as const },
      { href: "/proxies", label: "Прокси", icon: "proxies" as const },
      { href: "/alerts", label: "Алерты", icon: "alerts" as const },
    ],
  },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const live = useLiveConnected();

  const navLinkClass = (href: string) => {
    const active = href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
    return `flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition ${
      active
        ? "bg-neutral-800 text-neutral-100"
        : "text-neutral-400 hover:bg-neutral-900 hover:text-neutral-200"
    }`;
  };

  const links = NAV_SECTIONS.flatMap((section) => section.links);

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[232px_1fr]">
      <aside className="sticky top-0 hidden h-screen flex-col border-r border-neutral-800/80 bg-neutral-950/95 px-3 py-4 lg:flex">
        <Link href="/" className="mb-6 flex items-center gap-2 px-2 text-sm font-semibold">
          <span className="inline-block h-2 w-2 rounded-full bg-emerald-400" />
          avito-toolkit
        </Link>
        <nav className="flex flex-1 flex-col gap-5" aria-label="Основная навигация">
          {NAV_SECTIONS.map((section) => (
            <div key={section.title}>
              <p className="px-3 pb-1.5 text-[10px] uppercase tracking-wider text-neutral-600">
                {section.title}
              </p>
              <div className="flex flex-col gap-1">
                {section.links.map((link) => (
                  <Link key={link.href} href={link.href} className={navLinkClass(link.href)}>
                    <Icon name={link.icon} />
                    {link.label}
                  </Link>
                ))}
              </div>
            </div>
          ))}
        </nav>
        <a href={`${API_URL}/docs`} target="_blank" rel="noreferrer" className="rounded-lg px-3 py-2 text-xs text-neutral-500 transition hover:bg-neutral-900 hover:text-neutral-200">
          API-документация ↗
        </a>
      </aside>
      <div className="flex min-h-screen flex-col">
        <header className="sticky top-0 z-20 border-b border-neutral-800/80 bg-neutral-950/90 backdrop-blur">
          <div className="flex items-center justify-between gap-3 px-4 py-2.5 sm:px-6">
            <div className="flex items-center gap-3">
              <Link href="/" className="flex items-center gap-2 text-sm font-semibold lg:hidden">
                <span className="inline-block h-2 w-2 rounded-full bg-emerald-400" /> avito-toolkit
              </Link>
              <button type="button" onClick={() => setMenuOpen((value) => !value)} className="rounded-lg border border-neutral-800 px-3 py-1.5 text-xs text-neutral-300 lg:hidden" aria-expanded={menuOpen} aria-controls="mobile-navigation">
                {menuOpen ? "Закрыть" : "Меню"}
              </button>
            </div>
            <div className="flex items-center gap-2 sm:gap-4">
              <Suspense fallback={null}><SellerSwitcher /></Suspense>
              <span className={`hidden items-center gap-1.5 text-[11px] sm:flex ${live ? "text-emerald-300/90" : "text-neutral-500"}`} title={live ? "Обновления в реальном времени" : "Переподключение к событиям…"}>
                <span className={`inline-block h-1.5 w-1.5 rounded-full ${live ? "bg-emerald-400" : "bg-neutral-600"}`} />
                {live ? "live" : "офлайн"}
              </span>
              <ChatButton />
              <AlertsBell />
            </div>
          </div>
          {menuOpen ? <nav id="mobile-navigation" className="flex flex-col gap-1 border-t border-neutral-800 px-3 py-2" aria-label="Мобильная навигация">
            {links.map((link) => <Link key={link.href} href={link.href} onClick={() => setMenuOpen(false)} className={navLinkClass(link.href)}><Icon name={link.icon} />{link.label}</Link>)}
          </nav> : null}
        </header>
        <div className="flex-1">{children}</div>
        <footer className="border-t border-neutral-900 px-4 py-5 text-xs text-neutral-600 sm:px-6">avito-toolkit · аналитика рынка, конкуренты и рекомендации по ценам</footer>
      </div>
    </div>
  );
}
