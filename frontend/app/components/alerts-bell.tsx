"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { ackAlert, clearAlertsClient, fetchRecentAlertsClient, type Alert } from "@/lib/api";
import { useEvents } from "@/lib/events";
import { ALERT_TYPE_LABELS } from "@/lib/terms";
import { formatRelativeTime } from "@/lib/format";

export function AlertsBell() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);

  async function load() {
    const fresh = await fetchRecentAlertsClient();
    if (fresh) {
      setAlerts(fresh);
    }
  }

  useEffect(() => {
    load();
  }, []);

  useEvents((event) => {
    if (event.type === "alert.new") {
      load();
    }
  });

  useEffect(() => {
    if (!open) {
      return;
    }
    function onClick(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  const fresh = alerts.filter((alert) => alert.status === "new");

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="relative rounded-lg border border-neutral-800 px-2.5 py-1.5 text-sm text-neutral-300 transition hover:border-neutral-600"
        title="Уведомления"
      >
        🔔
        {fresh.length > 0 ? (
          <span className="absolute -right-1.5 -top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-amber-500 px-1 text-[10px] font-medium text-neutral-950">
            {fresh.length > 99 ? "99+" : fresh.length}
          </span>
        ) : null}
      </button>
      {open ? (
        <div className="absolute right-0 top-full z-40 mt-2 w-80 rounded-xl border border-neutral-700 bg-neutral-900 p-3 shadow-2xl">
          <div className="flex items-center justify-between pb-2">
            <p className="text-xs uppercase tracking-wider text-neutral-500">Уведомления</p>
            {fresh.length > 0 ? (
              <button
                type="button"
                onClick={async () => {
                  await clearAlertsClient({ status: "new" });
                  await load();
                }}
                className="text-xs text-neutral-400 hover:text-neutral-200"
              >
                Прочитать все
              </button>
            ) : null}
          </div>
          {alerts.length === 0 ? (
            <p className="py-4 text-center text-xs text-neutral-500">Пока пусто</p>
          ) : (
            <ul className="flex max-h-80 flex-col gap-1 overflow-y-auto">
              {alerts.slice(0, 12).map((alert) => (
                <li
                  key={alert.id}
                  className={`rounded-lg border px-2.5 py-2 text-xs ${
                    alert.status === "new"
                      ? "border-amber-500/30 bg-amber-500/5"
                      : "border-neutral-800 bg-neutral-950/40"
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <span className="font-medium text-neutral-200">
                      {ALERT_TYPE_LABELS[alert.type] ?? alert.type}
                    </span>
                    <span className="whitespace-nowrap text-neutral-500">
                      {formatRelativeTime(alert.created_at)}
                    </span>
                  </div>
                  {alert.payload?.title ? (
                    <p className="mt-0.5 truncate text-neutral-400">
                      {String(alert.payload.title)}
                    </p>
                  ) : null}
                  {alert.status === "new" ? (
                    <button
                      type="button"
                      onClick={async () => {
                        await ackAlert(alert.id);
                        await load();
                      }}
                      className="mt-1 text-[11px] text-sky-300/80 hover:underline"
                    >
                      Прочитано
                    </button>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
          <Link
            href="/#alerts"
            onClick={() => setOpen(false)}
            className="mt-2 block rounded-lg border border-neutral-800 px-3 py-1.5 text-center text-xs text-neutral-300 transition hover:border-neutral-600"
          >
            Все алерты
          </Link>
        </div>
      ) : null}
    </div>
  );
}
