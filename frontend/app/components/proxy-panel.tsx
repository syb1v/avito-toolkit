"use client";

import { useCallback, useEffect, useState } from "react";

import { useConfirm } from "@/app/components/confirm";
import { InfoHint } from "@/app/components/info-hint";
import { Modal } from "@/app/components/modal";
import { useToast } from "@/app/components/toast";
import {
  checkProxiesClient,
  createProxyClient,
  deleteProxyClient,
  fetchProxiesClient,
  updateProxyClient,
  type ProxyStatus,
} from "@/lib/api";
import { formatRelativeTime } from "@/lib/format";

const POLL_INTERVAL_MS = 20000;

export function ProxyPanel() {
  const [status, setStatus] = useState<ProxyStatus | null>(null);
  const [checking, setChecking] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [addText, setAddText] = useState("");
  const [addNote, setAddNote] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const toast = useToast();
  const confirm = useConfirm();

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
    toast.push("info", "Проверяю прокси: канал + доступность Авито");
    const ok = await checkProxiesClient();
    await load();
    setChecking(false);
    toast.push(ok ? "success" : "error", ok ? "Проверка завершена" : "Не удалось проверить прокси");
  }

  async function addProxies() {
    const lines = addText
      .split(/[\n;,]+/)
      .map((line) => line.trim())
      .filter(Boolean);
    if (lines.length === 0) {
      toast.push("error", "Вставьте хотя бы один прокси");
      return;
    }
    let added = 0;
    for (const line of lines) {
      const result = await createProxyClient(line, addNote.trim() || null);
      if (result.ok) {
        added += 1;
      } else {
        toast.push("error", `${line.slice(0, 24)}…: ${result.error}`);
      }
    }
    if (added > 0) {
      toast.push("success", `Добавлено прокси: ${added}`);
      setAddText("");
      setAddNote("");
      setAddOpen(false);
      await load();
    }
  }

  async function toggle(entryId: string, enabled: boolean) {
    setBusyId(entryId);
    const result = await updateProxyClient(entryId, { enabled });
    setBusyId(null);
    if (!result.ok) {
      toast.push("error", result.error);
      return;
    }
    toast.push("info", enabled ? "Прокси включён" : "Прокси выключен");
    await load();
  }

  async function remove(entryId: string, label: string) {
    const ok = await confirm({
      title: "Удалить прокси?",
      text: `${label} будет удалён из пула.`,
      confirmLabel: "Удалить",
      danger: true,
    });
    if (!ok) {
      return;
    }
    setBusyId(entryId);
    const result = await deleteProxyClient(entryId);
    setBusyId(null);
    if (!result.ok) {
      toast.push("error", result.error);
      return;
    }
    toast.push("success", "Прокси удалён");
    await load();
  }

  if (status === null) {
    return null;
  }

  const button =
    "rounded-lg border border-neutral-700 px-3 py-1 text-xs text-neutral-300 transition hover:border-neutral-500 disabled:opacity-50";

  return (
    <section className="rounded-xl border border-neutral-800 bg-neutral-900/60 p-4 sm:p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center">
          <h2 className="text-base font-medium sm:text-lg">Прокси</h2>
          <InfoHint
            title="Прокси простыми словами"
            text="Прокси — это промежуточные адреса, через которые уходят запросы к Авито. Если Авито не пускает робота напрямую, он может пустить через «чужой» адрес. Проверка показывает: жив ли адрес (IP и задержка) и пускает ли Авито (метка «Авито блокирует» — не пускает; пусто — всё хорошо). 429 — это «не части», а не запрет: браузер через тот же адрес обычно работает. Прокси можно добавить, выключить и удалить прямо здесь."
          />
        </div>
        <div className="flex flex-wrap items-center gap-3 text-xs">
          {status.configured ? (
            <span className="text-neutral-400">
              живых {status.alive}/{status.count}
              {status.in_cooldown > 0 ? ` · в кулдауне ${status.in_cooldown}` : ""}
              {status.antibot_blocked > 0
                ? ` · Авито блокирует ${status.antibot_blocked}`
                : ""}
            </span>
          ) : null}
          <button
            type="button"
            onClick={() => setAddOpen(true)}
            className="rounded-lg border border-sky-500/40 bg-sky-500/10 px-3 py-1.5 text-xs text-sky-200 transition hover:bg-sky-500/20"
          >
            + Добавить прокси
          </button>
          {status.configured ? (
            <button
              type="button"
              onClick={check}
              disabled={checking}
              className="rounded-lg border border-sky-500/40 bg-sky-500/10 px-3 py-1.5 text-xs text-sky-200 transition hover:bg-sky-500/20 disabled:opacity-50"
            >
              {checking ? "Проверка…" : "Проверить"}
            </button>
          ) : null}
        </div>
      </div>

      {status.enabled ? (
        <p className="mt-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-200/90">
          Прокси работают: поиски без закреплённого адреса берут живые прокси из
          общего пула, а аккаунты с закреплённым прокси ходят через него.
        </p>
      ) : (
        <p className="mt-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200/90">
          Общий пул сейчас выключен: поиски без закреплённого адреса ходят с вашего
          IP напрямую. Если у аккаунта закреплён прокси (кнопка «Прокси» в
          «Аккаунтах»), он всё равно используется — обход идёт через него.
        </p>
      )}

      {!status.configured ? (
        <p className="mt-3 text-sm text-neutral-500">
          Прокси пока нет — нажмите «+ Добавить прокси» и вставьте адреса
          (например, http://user:pass@host:port или host:port:user:pass).
        </p>
      ) : (
        <ul className="mt-3 flex flex-col gap-2">
          {status.entries.map((entry) => (
            <li
              key={entry.id}
              className={`flex flex-wrap items-center justify-between gap-2 rounded-lg border border-neutral-800 px-3 py-2 text-xs ${
                entry.enabled ? "bg-neutral-950/60" : "bg-neutral-950/20 opacity-70"
              }`}
            >
              <div className="flex min-w-0 items-center gap-2">
                <span
                  className={`inline-block h-2 w-2 shrink-0 rounded-full ${
                    !entry.enabled
                      ? "bg-neutral-600"
                      : entry.healthy
                        ? "bg-emerald-400"
                        : entry.antibot_blocked
                          ? "bg-amber-400"
                          : "bg-red-500"
                  }`}
                />
                <span className="truncate font-mono text-neutral-300">{entry.label}</span>
                {entry.note ? (
                  <span className="truncate text-neutral-600">{entry.note}</span>
                ) : null}
                {!entry.enabled ? (
                  <span className="rounded-full border border-neutral-700 px-2 py-0.5 text-[10px] text-neutral-400">
                    выключен
                  </span>
                ) : null}
              </div>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-neutral-500">
                {entry.enabled && entry.exit_ip ? <span>IP: {entry.exit_ip}</span> : null}
                {entry.enabled && entry.latency_ms ? <span>{entry.latency_ms} мс</span> : null}
                {entry.enabled && entry.antibot_blocked ? (
                  <span className="text-amber-300">
                    Авито блокирует · {Math.ceil(entry.antibot_seconds_left / 60)} мин
                  </span>
                ) : entry.enabled && !entry.healthy && entry.cooldown_seconds_left > 0 ? (
                  <span className="text-red-300">
                    кулдаун {entry.cooldown_seconds_left} с
                  </span>
                ) : null}
                {entry.enabled && entry.last_ok ? (
                  <span>ok {formatRelativeTime(entry.last_ok)}</span>
                ) : null}
                {entry.enabled && entry.last_error ? (
                  <span className="max-w-[220px] truncate text-red-400/80" title={entry.last_error}>
                    {entry.last_error}
                  </span>
                ) : null}
                <button
                  type="button"
                  onClick={() => toggle(entry.id, !entry.enabled)}
                  disabled={busyId === entry.id}
                  className={button}
                >
                  {entry.enabled ? "Выключить" : "Включить"}
                </button>
                <button
                  type="button"
                  onClick={() => remove(entry.id, entry.label)}
                  disabled={busyId === entry.id}
                  className="rounded-lg border border-red-500/30 px-3 py-1 text-xs text-red-300 transition hover:border-red-500/60 disabled:opacity-50"
                >
                  Удалить
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      <Modal
        open={addOpen}
        onClose={() => setAddOpen(false)}
        title="Добавить прокси"
        subtitle="По одному в строке. Форматы: http://user:pass@host:port, host:port:user:pass, socks5://user:pass@host:port, host:port"
        maxWidth="max-w-xl"
        footer={
          <>
            <button type="button" onClick={() => setAddOpen(false)} className={button}>
              Отмена
            </button>
            <button
              type="button"
              onClick={addProxies}
              className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-4 py-1.5 text-xs text-emerald-200 transition hover:bg-emerald-500/20"
            >
              Добавить
            </button>
          </>
        }
      >
        <textarea
          value={addText}
          onChange={(event) => setAddText(event.target.value)}
          rows={6}
          placeholder={"http://user:pass@host:5500\nhost:5500:user:pass\nsocks5://user:pass@host:1080"}
          className="w-full rounded-lg border border-neutral-800 bg-neutral-950 px-3 py-2 font-mono text-[11px] text-neutral-200 outline-none focus:border-sky-500/60"
        />
        <label className="mt-3 flex flex-col gap-1 text-xs text-neutral-400">
          Заметка (необязательно)
          <input
            value={addNote}
            onChange={(event) => setAddNote(event.target.value)}
            placeholder="например: резидентные, Армения"
            className="rounded-lg border border-neutral-800 bg-neutral-950 px-3 py-2 text-sm text-neutral-200 outline-none focus:border-sky-500/60"
          />
        </label>
      </Modal>
    </section>
  );
}
