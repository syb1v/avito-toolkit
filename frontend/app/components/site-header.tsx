import Link from "next/link";

import { API_URL } from "@/lib/api";

const NAV_LINKS = [
  { href: "/", label: "Поиски" },
  { href: "/our-listings", label: "Наши объявления" },
];

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-20 border-b border-neutral-800/80 bg-neutral-950/85 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-3 sm:px-6">
        <Link
          href="/"
          className="flex items-center gap-2 text-sm font-semibold tracking-tight"
        >
          <span className="inline-block h-2 w-2 rounded-full bg-emerald-400" />
          avito-toolkit
        </Link>
        <nav className="flex items-center gap-1 text-sm">
          {NAV_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="rounded-lg px-2.5 py-2 text-neutral-400 transition hover:bg-neutral-900 hover:text-neutral-100 sm:px-3"
            >
              {link.label}
            </Link>
          ))}
          <a
            href={`${API_URL}/docs`}
            target="_blank"
            rel="noreferrer"
            className="rounded-lg px-2.5 py-2 text-neutral-500 transition hover:bg-neutral-900 hover:text-neutral-200 sm:px-3"
          >
            API
          </a>
        </nav>
      </div>
    </header>
  );
}
