"use client";

import { useCallback, useEffect, useState } from "react";

import { fetchProgressClient, triggerCrawl, type SearchProgress } from "@/lib/api";
import { useToast } from "@/app/components/toast";
import { InfoHint } from "@/app/components/info-hint";
import { formatRelativeTime } from "@/lib/format";

const POLL_INTERVAL_MS = 3000;

const STAGE_LABELS: Record<string, string> = {
  queued: "В очереди",
  pausing: "Подготовка",
  crawl: "Сбор страниц",
  moderation: "AI-модерация",
  analytics: "Аналитика",
  matching: "Матчинг SKU",
  alerts: "Алерты",
  done: "Готово",
};

const STATUS_LABELS: Record<string, string> = {
  idle: "ожидание",
  queued: "в очереди",
  running: "выполняется",
  done: "завершён",
  failed: "ошибка",
};

const STATUS_STYLES: Record<string, string> = {
  idle: "border-neutral-700 bg-neutral-800 text-neutral-400",
  queued: "border-amber-500/30 bg-amber-500/10 text-amber-200",
  running: "border-sky-500/30 bg-sky-500/10 text-sky-200",
  done: "border-emerald-500/30 bg-emerald-500/15 text-emerald-300",
  failed: "border-red-500/30 bg-red-500/10 text-red-300",
};

export function CrawlPanel({ searchId }: { searchId: string }) {
  const [progress, setProgress] = useState<SearchProgress | null>(null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  const load = useCallback(async () => {
    const data = await fetchProgressClient(searchId);
    setProgress(data);
  }, [searchId]);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      const data = await fetchProgressClient(searchId);
      if (!cancelled) {
        setProgress(data);
      }
    };
    tick();
    const timer = setInterval(tick, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [searchId]);

  async function start() {
    setBusy(true);
    // Мгновенная обратная связь: сразу показываем «в очереди», не ждём воркера.
    setProgress((current) => ({
      search_id: searchId,
      status: "queued",
      stage: "queued",
      page: 0,
      max_pages: current?.max_pages ?? 0,
      listings_seen: 0,
      result: null,
      error: null,
      updated_at: new Date().toISOString(),
      last_crawl_at: current?.last_crawl_at ?? null,
    }));
    const ok = await triggerCrawl(searchId);
    await load();
    setBusy(false);
    if (ok) {
      toast.push("info", "Обход поставлен в очередь");
    } else {
      toast.push("error", "Не удалось запустить обход");
    }
  }

  const status = progress?.status ?? "idle";
  const running = status === "running";
  const queued = status === "queued";
  const stage = progress?.stage ?? null;
  const page = progress?.page ?? 0;
  const maxPages = progress?.max_pages ?? 0;
  const listingsSeen = progress?.listings_seen ?? 0;

  let percent = 0;
  let indeterminate = false;
  if (queued) {
    indeterminate = true;
  } else if (running && stage === "crawl") {
    if (maxPages > 0) {
      percent = Math.min(100, Math.round((page / maxPages) * 100));
    } else {
      indeterminate = true;
    }
  } else if (running) {
    indeterminate = true;
  } else if (status === "done") {
    percent = 100;
  }

  return (
    <section className="rounded-xl border border-neutral-800 bg-neutral-900/60 p-4 sm:p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <h2 className="text-base font-medium sm:text-lg">Обход</h2>
          <InfoHint
            title="Пайплайн обхода"
            text="Сбор страниц (браузер-first, при блокировке — HTTP) → аналитика (IQR, медиана и перцентили) → матчинг ваших SKU → алерты. Прогресс обновляется автоматически; страницы идут с паузами 8–20 секунд."
          />
          <span
            className={`rounded-full border px-2.5 py-0.5 text-xs ${
              STATUS_STYLES[status] ?? STATUS_STYLES.idle
            }`}
          >
            {STATUS_LABELS[status] ?? status}
          </span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-neutral-500">
            последний сбор: {formatRelativeTime(progress?.last_crawl_at)}
          </span>
          <button
            type="button"
            onClick={start}
            disabled={running || queued || busy}
            className="rounded-lg border border-sky-500/40 bg-sky-500/10 px-3 py-1.5 text-xs text-sky-200 transition hover:bg-sky-500/20 disabled:opacity-50"
          >
            {running
              ? "Идёт обход…"
              : queued
                ? "В очереди…"
                : busy
                  ? "Запуск…"
                  : "Запустить обход"}
          </button>
        </div>
      </div>

      <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-neutral-800">
        <div
          className={`h-full rounded-full transition-all duration-500 ${
            indeterminate
              ? "w-1/3 animate-pulse bg-sky-400/70"
              : "bg-emerald-500/70"
          }`}
          style={indeterminate ? undefined : { width: `${percent}%` }}
        />
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-neutral-400">
        {queued ? (
          <span className="text-amber-200/90">
            Обход в очереди — воркер начнёт в течение нескольких секунд
          </span>
        ) : running ? (
          <>
            <span>{STAGE_LABELS[stage ?? ""] ?? stage ?? "работа"}</span>
            {stage === "crawl" ? (
              <span>
                {maxPages > 0
                  ? `страница ${page} из ${maxPages}`
                  : `страница ${page} · без лимита`}
              </span>
            ) : null}
            <span>найдено лотов: {listingsSeen}</span>
          </>
        ) : progress?.error ? (
          <span className="text-red-300">{progress.error}</span>
        ) : progress?.result ? (
          <span>
            собрано страниц: {String(progress.result.pages_fetched ?? "—")} · новых:{" "}
            {String(progress.result.new_listings ?? "—")} · изменений цены:{" "}
            {String(progress.result.price_changes ?? "—")}
          </span>
        ) : (
          <span>Обход запускается планировщиком по cron или кнопкой выше.</span>
        )}
      </div>
    </section>
  );
}
