import type { Metadata } from "next";

import { AppShell } from "@/app/components/app-shell";
import { ConfirmProvider } from "@/app/components/confirm";
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
            <AppShell>{children}</AppShell>
          </ConfirmProvider>
        </ToastProvider>
      </body>
    </html>
  );
}
