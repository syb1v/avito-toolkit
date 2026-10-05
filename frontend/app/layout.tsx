import type { Metadata } from "next";

import { ConfirmProvider } from "@/app/components/confirm";
import { SiteHeader } from "@/app/components/site-header";
import { ToastProvider } from "@/app/components/toast";

import "./globals.css";

export const metadata: Metadata = {
  title: "Avito Toolkit",
  description: "Аналитика рынка Авито и управление объявлениями",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ru">
      <body className="min-h-screen bg-neutral-950 text-neutral-100 antialiased">
        <ToastProvider>
          <ConfirmProvider>
            <SiteHeader />
            {children}
            <footer className="mx-auto max-w-6xl px-4 pb-10 pt-2 text-xs text-neutral-600 sm:px-6">
              avito-toolkit · аналитика рынка, конкуренты и рекомендации по ценам
            </footer>
          </ConfirmProvider>
        </ToastProvider>
      </body>
    </html>
  );
}
