"use client";

import { useCallback, useEffect, useState } from "react";

import { InfoHint } from "@/app/components/info-hint";
import {
  checkProxiesClient,
  fetchProxiesClient,
  type ProxyStatus,
} from "@/lib/api";
import { formatRelativeTime } from "@/lib/format";

const POLL_INTERVAL_MS = 20000;

export function ProxyPanel() {
  const [status, setStatus] = useState<ProxyStatus | null>(null);
  const [checking, setChecking] = useState(false);

  const load = useCallback(async () => {
    setStatus(await fetchProxiesClient());
  }, []);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      const fresh = await fetchProxiesClient();
      if (!cancelled) {
        setStatus(fresh);
      }
    };
    tick();
    const timer = setInterval(tick, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  async function check() {
    setChecking(true);
    await checkProxiesClient();
    await load();
    setChecking(false);
  }

  if (status === null) {
    return null;
  }

  if (!status.configured) {
    return (
      <section className="rounded-xl border border-neutral-800 bg-neutral-900/60 p-4 sm:p-5">
        <div className="flex items-center">
          <h2 className="text-base font-medium sm:text-lg">Прокси</h2>
          <InfoHint
            title="Как включить пул прокси"
            text="Задайте PROXY_LIST в .env (через запятую или с новой строки): http://user:pass@host:port, socks5://host:port, host:port:user:pass. Ротация: PROXY_ROTATION=round_robin|random. Упавшие прокси уходят в кулдаун и возвращаются после healthcheck."
          />
        </div>
        <p className="mt-2 text-sm text-neutral-500">
          Пул не настроен — запросы идут с вашего IP. Добавьте PROXY_LIST в .env и
          перезапустите воркер, чтобы включить ротацию и автоматический healthcheck.
        </p>
      </section>
    );
  }

  return (
    <section className="rounded-xl border border-neutral-800 bg-neutral-900/60 p-4 sm:p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center">
          <h2 className="text-base font-medium sm:text-lg">Прокси</h2>
          <InfoHint
            title="Как работают прокси"
            text="Ротация по кругу или случайно; на каждый запрос выбирается живой прокси (не в кулдауне). Проверка: канал (внешний IP и задержка) + Авито (robots.txt) + поисковая выдача обычным HTTP-клиентом. Если у HTTP-клиента 429 — это лимит для не-браузерных запросов, а не блокировка: реальный Chromium с cookies через этот же прокси может работать (это проверяет кнопка «Проверить» у аккаунта или обход). Для браузера нужен http(s) с логином/паролем: Chromium не умеет авторизацию в socks5."
          />
        </div>
        <div className="flex flex-wrap items-center gap-3 text-xs">
          <span className="text-neutral-400">
            режим: {status.mode} · живых {status.alive}/{status.count}
            {status.in_cooldown > 0 ? ` · в кулдауне ${status.in_cooldown}` : ""}
            {status.antibot_blocked > 0
              ? ` · Авито блокирует ${status.antibot_blocked}`
              : ""}
          </span>
          <button
            type="button"
            onClick={check}
            disabled={checking}
            className="rounded-lg border border-sky-500/40 bg-sky-500/10 px-3 py-1.5 text-xs text-sky-200 transition hover:bg-sky-500/20 disabled:opacity-50"
          >
            {checking ? "Проверка…" : "Проверить"}
          </button>
        </div>
      </div>

      {!status.enabled ? (
        <p className="mt-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200/90">
          Глобальный пул выключен (PROXY_ENABLED=false): поиски без привязанного прокси
          идут с вашего IP. У аккаунтов с закреплённым прокси (кнопка «Прокси»
          в «Аккаунтах») обход идёт через него независимо от этого флага.
        </p>
      ) : null}

      <ul className="mt-3 flex flex-col gap-2">
        {status.entries.map((entry) => (
          <li
            key={entry.label}
            className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-neutral-800 bg-neutral-950/60 px-3 py-2 text-xs"
          >
            <div className="flex min-w-0 items-center gap-2">
              <span
                className={`inline-block h-2 w-2 shrink-0 rounded-full ${
                  entry.healthy
                    ? "bg-emerald-400"
                    : entry.antibot_blocked
                      ? "bg-amber-400"
                      : "bg-red-500"
                }`}
              />
              <span className="truncate font-mono text-neutral-300">{entry.label}</span>
            </div>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-neutral-500">
              {entry.exit_ip ? <span>IP: {entry.exit_ip}</span> : null}
              {entry.latency_ms ? <span>{entry.latency_ms} мс</span> : null}
              {entry.antibot_blocked ? (
                <span className="text-amber-300">
                  Авито блокирует · {Math.ceil(entry.antibot_seconds_left / 60)} мин
                </span>
              ) : !entry.healthy ? (
                <span className="text-red-300">
                  кулдаун {entry.cooldown_seconds_left} с
                </span>
              ) : null}
              {entry.last_ok ? <span>ok {formatRelativeTime(entry.last_ok)}</span> : null}
              {entry.last_error ? (
                <span className="max-w-[220px] truncate text-red-400/80">
                  {entry.last_error}
                </span>
              ) : null}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
