"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { InfoHint } from "@/app/components/info-hint";
import { fetchDashboardClient, type Dashboard } from "@/lib/api";

const POLL_INTERVAL_MS = 5000;

const STAGE_LABELS: Record<string, string> = {
  crawl: "сбор страниц",
  moderation: "AI-модерация",
  analytics: "аналитика",
  matching: "матчинг",
  alerts: "алерты",
};

export function SystemStatusPanel({ initial }: { initial: Dashboard | null }) {
  const [data, setData] = useState<Dashboard | null>(initial);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      const fresh = await fetchDashboardClient();
      if (!cancelled && fresh) {
        setData(fresh);
      }
    };
    const timer = setInterval(tick, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  const workerAlive = data?.worker_alive ?? false;
  const queues = data?.queues ?? { crawl: 0, analytics: 0 };
  const active = data?.active_crawls ?? [];

  return (
    <section className="rounded-xl border border-neutral-800 bg-neutral-900/60 p-4 sm:p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center">
          <h2 className="text-base font-medium sm:text-lg">Статус системы</h2>
          <InfoHint
            title="Что здесь видно"
            text="Воркер — процесс, который выполняет обходы и аналитику (зелёная точка = heartbeat свежий). Очереди — сколько задач ждёт выполнения. Активные обходы показывают стадию и страницу прямо сейчас."
          />
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
          <span className="flex items-center gap-1.5">
            <span
              className={`inline-block h-2 w-2 rounded-full ${
                workerAlive ? "animate-pulse bg-emerald-400" : "bg-red-500"
              }`}
            />
            {workerAlive ? "воркер на связи" : "воркер не отвечает"}
          </span>
          <span className="text-neutral-400">
            очередь обходов: {queues.crawl} · аналитика: {queues.analytics}
          </span>
        </div>
      </div>

      {active.length === 0 ? (
        <p className="mt-3 text-xs text-neutral-500">
          Активных обходов нет — планировщик запустит их по расписанию поисков.
        </p>
      ) : (
        <ul className="mt-3 flex flex-col gap-2">
          {active.map((crawl) => {
            const percent =
              crawl.stage === "crawl" && crawl.max_pages
                ? Math.min(100, Math.round(((crawl.page ?? 0) / crawl.max_pages) * 100))
                : 0;
            return (
              <li
                key={crawl.search_id}
                className="rounded-lg border border-neutral-800 bg-neutral-950/60 px-3 py-2"
              >
                <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
                  <Link
                    href={`/searches/${crawl.search_id}`}
                    className="truncate hover:underline"
                  >
                    {crawl.search_name ?? crawl.search_id}
                  </Link>
                  <span className="text-xs text-sky-200">
                    {STAGE_LABELS[crawl.stage ?? ""] ?? crawl.stage ?? "работа"}
                    {crawl.stage === "crawl" && crawl.max_pages
                      ? ` · стр. ${crawl.page ?? 0}/${crawl.max_pages}`
                      : ""}
                    {crawl.listings_seen ? ` · лотов ${crawl.listings_seen}` : ""}
                  </span>
                </div>
                <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-neutral-800">
                  <div
                    className={`h-full rounded-full ${
                      crawl.stage === "crawl"
                        ? "bg-emerald-500/70 transition-all duration-500"
                        : "w-1/3 animate-pulse bg-sky-400/70"
                    }`}
                    style={
                      crawl.stage === "crawl" ? { width: `${percent}%` } : undefined
                    }
                  />
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
