"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { InfoHint } from "@/app/components/info-hint";
import {
  type Account,
  type Search,
  createSearchClient,
  deleteSearchClient,
  fetchSearches,
  triggerCrawl,
  updateSearchClient,
} from "@/lib/api";

type FormState = {
  id: string | null;
  name: string;
  url: string;
  cron: string;
  priority: string;
  maxPages: string;
  include: string;
  exclude: string;
  city: string;
  regions: string;
  excludeRegions: string;
  accountId: string;
};

const EMPTY_FORM: FormState = {
  id: null,
  name: "",
  url: "",
  cron: "0 */6 * * *",
  priority: "100",
  maxPages: "0",
  include: "",
  exclude: "",
  city: "",
  regions: "",
  excludeRegions: "",
  accountId: "",
};

function listToText(value: unknown): string {
  if (Array.isArray(value)) {
    return value.map(String).join(", ");
  }
  if (typeof value === "string") {
    return value;
  }
  return "";
}

function parseInclude(text: string): string[][] {
  return text
    .split("\n")
    .map((line) =>
      line
        .split(",")
        .map((chunk) => chunk.trim())
        .filter(Boolean),
    )
    .filter((group) => group.length > 0);
}

function parseExclude(text: string): string[] {
  return text
    .split(/[\n,;]+/)
    .map((chunk) => chunk.trim())
    .filter(Boolean);
}

function includeToText(params: Record<string, unknown> | null): string {
  const groups = params?.keyword_groups;
  if (!Array.isArray(groups)) {
    return "";
  }
  return groups
    .filter((group): group is string[] => Array.isArray(group))
    .map((group) => group.join(", "))
    .join("\n");
}

function excludeToText(params: Record<string, unknown> | null): string {
  const list = params?.exclude_keywords;
  if (Array.isArray(list)) {
    return list.map(String).join(", ");
  }
  if (typeof list === "string") {
    return list;
  }
  return "";
}

function maxPagesOf(params: Record<string, unknown> | null): string {
  const value = params?.max_pages;
  return typeof value === "number" ? String(value) : "0";
}

export function SearchManager({
  initial,
  accounts,
}: {
  initial: Search[];
  accounts: Account[];
}) {
  const router = useRouter();
  const [items, setItems] = useState(initial);
  const [form, setForm] = useState<FormState | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const accountName = (id: string | null) =>
    accounts.find((account) => account.id === id)?.name ?? "—";

  async function refresh() {
    setItems(await fetchSearches());
    router.refresh();
  }

  function openCreate() {
    setForm({ ...EMPTY_FORM, accountId: accounts[0]?.id ?? "" });
    setError(null);
    setMessage(null);
  }

  function openEdit(search: Search) {
    setForm({
      id: search.id,
      name: search.name,
      url: search.url,
      cron: search.schedule_cron,
      priority: String(search.priority),
      maxPages: maxPagesOf(search.params),
      include: includeToText(search.params),
      exclude: excludeToText(search.params),
      city: typeof search.params?.city === "string" ? search.params.city : "",
      regions: listToText(search.params?.regions),
      excludeRegions: listToText(search.params?.exclude_regions),
      accountId: search.account_id ?? "",
    });
    setError(null);
    setMessage(null);
  }

  async function submit() {
    if (!form) {
      return;
    }
    const name = form.name.trim();
    const url = form.url.trim();
    if (!name || !url) {
      setError("Заполните название и ссылку на выдачу");
      return;
    }
    const current = items.find((item) => item.id === form.id);
    const params: Record<string, unknown> = {
      ...(current?.params ?? {}),
      keyword_groups: parseInclude(form.include),
      exclude_keywords: parseExclude(form.exclude),
      max_pages: Math.max(0, Number(form.maxPages) || 0),
      city: form.city.trim().toLowerCase().replace(/\s+/g, "-"),
      regions: parseExclude(form.regions),
      exclude_regions: parseExclude(form.excludeRegions),
    };
    const payload = {
      name,
      url,
      params,
      schedule_cron: form.cron.trim() || "0 */6 * * *",
      priority: Number(form.priority) || 100,
      account_id: form.accountId || null,
    };
    setBusy("save");
    const result = form.id
      ? await updateSearchClient(form.id, payload)
      : await createSearchClient(payload);
    setBusy(null);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setForm(null);
    setMessage(form.id ? "Поиск обновлён" : "Поиск добавлен");
    await refresh();
  }

  async function toggleActive(search: Search) {
    setBusy(search.id);
    const result = await updateSearchClient(search.id, { is_active: !search.is_active });
    setBusy(null);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    await refresh();
  }

  async function remove(search: Search) {
    if (!window.confirm(`Удалить поиск «${search.name}» со всей собранной выдачей?`)) {
      return;
    }
    setBusy(search.id);
    const result = await deleteSearchClient(search.id);
    setBusy(null);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    await refresh();
  }

  async function crawl(search: Search) {
    setBusy(search.id);
    const ok = await triggerCrawl(search.id);
    setBusy(null);
    setMessage(ok ? `Обход «${search.name}» поставлен в очередь` : null);
    if (!ok) {
      setError("Не удалось запустить обход");
    }
  }

  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center">
          <h2 className="text-lg font-medium">Поиски</h2>
          <InfoHint
            title="Как управлять поисками"
            text="Поиск — это URL выдачи Авито и фильтры. Включение (include) — все строки-группы должны совпасть (AND), альтернативы в строке через запятую (OR). Исключение (exclude) — любое из стоп-слов убирает объявление из статистики. max_pages=0 — обходить все страницы, пока Авито отдаёт выдачу. Аккаунт определяет, чей профиль с cookies использовать."
          />
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-neutral-500">{items.length} шт.</span>
          <button
            type="button"
            onClick={openCreate}
            className="rounded-lg border border-sky-500/40 bg-sky-500/10 px-3 py-1.5 text-xs text-sky-200 transition hover:bg-sky-500/20"
          >
            + Добавить поиск
          </button>
        </div>
      </div>

      {message ? <p className="text-xs text-emerald-300">{message}</p> : null}
      {error ? <p className="text-xs text-red-300">{error}</p> : null}

      {form ? (
        <div className="rounded-xl border border-sky-500/25 bg-neutral-900/70 p-4 sm:p-5">
          <h3 className="text-sm font-medium text-sky-100">
            {form.id ? "Редактирование поиска" : "Новый поиск"}
          </h3>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <label className="flex flex-col gap-1 text-xs text-neutral-400">
              Название
              <input
                value={form.name}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
                placeholder="Devialet Dione"
                className="rounded-lg border border-neutral-800 bg-neutral-950 px-3 py-2 text-sm text-neutral-200 outline-none focus:border-sky-500/60"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-neutral-400">
              Аккаунт
              <select
                value={form.accountId}
                onChange={(event) => setForm({ ...form, accountId: event.target.value })}
                className="rounded-lg border border-neutral-800 bg-neutral-950 px-3 py-2 text-sm text-neutral-200 outline-none focus:border-sky-500/60"
              >
                <option value="">— по умолчанию —</option>
                {accounts
                  .filter((account) => account.role !== "seller")
                  .map((account) => (
                    <option key={account.id} value={account.id}>
                      {account.name}
                      {account.is_default ? " (основной)" : ""}
                    </option>
                  ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-xs text-neutral-400 sm:col-span-2">
              Ссылка на выдачу Авито
              <input
                value={form.url}
                onChange={(event) => setForm({ ...form, url: event.target.value })}
                placeholder="https://www.avito.ru/all?q=..."
                className="rounded-lg border border-neutral-800 bg-neutral-950 px-3 py-2 font-mono text-xs text-neutral-200 outline-none focus:border-sky-500/60"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-neutral-400">
              Cron (UTC)
              <input
                value={form.cron}
                onChange={(event) => setForm({ ...form, cron: event.target.value })}
                placeholder="0 */6 * * *"
                className="rounded-lg border border-neutral-800 bg-neutral-950 px-3 py-2 font-mono text-xs text-neutral-200 outline-none focus:border-sky-500/60"
              />
            </label>
            <div className="grid grid-cols-2 gap-3">
              <label className="flex flex-col gap-1 text-xs text-neutral-400">
                Приоритет
                <input
                  value={form.priority}
                  onChange={(event) => setForm({ ...form, priority: event.target.value })}
                  inputMode="numeric"
                  className="rounded-lg border border-neutral-800 bg-neutral-950 px-3 py-2 text-sm text-neutral-200 outline-none focus:border-sky-500/60"
                />
              </label>
              <label className="flex flex-col gap-1 text-xs text-neutral-400">
                Страниц (0=∞)
                <input
                  value={form.maxPages}
                  onChange={(event) => setForm({ ...form, maxPages: event.target.value })}
                  inputMode="numeric"
                  className="rounded-lg border border-neutral-800 bg-neutral-950 px-3 py-2 text-sm text-neutral-200 outline-none focus:border-sky-500/60"
                />
              </label>
            </div>
            <label className="flex flex-col gap-1 text-xs text-neutral-400">
              Город выдачи (slug)
              <input
                value={form.city}
                onChange={(event) => setForm({ ...form, city: event.target.value })}
                placeholder="moskva (пусто — как в ссылке)"
                className="rounded-lg border border-neutral-800 bg-neutral-950 px-3 py-2 font-mono text-xs text-neutral-200 outline-none focus:border-sky-500/60"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-neutral-400">
              Города: только эти
              <input
                value={form.regions}
                onChange={(event) => setForm({ ...form, regions: event.target.value })}
                placeholder="moskva, sankt-peterburg"
                className="rounded-lg border border-neutral-800 bg-neutral-950 px-3 py-2 font-mono text-xs text-neutral-200 outline-none focus:border-sky-500/60"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-neutral-400 sm:col-span-2">
              Исключить города
              <input
                value={form.excludeRegions}
                onChange={(event) =>
                  setForm({ ...form, excludeRegions: event.target.value })
                }
                placeholder="drugie-goroda (лоты останутся в выдаче, но вне расчёта)"
                className="rounded-lg border border-neutral-800 bg-neutral-950 px-3 py-2 font-mono text-xs text-neutral-200 outline-none focus:border-sky-500/60"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-neutral-400">
              Включение (строка = AND-группа, альтернативы через запятую)
              <textarea
                value={form.include}
                onChange={(event) => setForm({ ...form, include: event.target.value })}
                rows={3}
                placeholder={"devialet\ndione, dion"}
                className="rounded-lg border border-neutral-800 bg-neutral-950 px-3 py-2 text-sm text-neutral-200 outline-none focus:border-sky-500/60"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-neutral-400">
              Исключение (стоп-слова через запятую)
              <textarea
                value={form.exclude}
                onChange={(event) => setForm({ ...form, exclude: event.target.value })}
                rows={3}
                placeholder="чехол, копия, реплика, ремонт"
                className="rounded-lg border border-neutral-800 bg-neutral-950 px-3 py-2 text-sm text-neutral-200 outline-none focus:border-sky-500/60"
              />
            </label>
          </div>
          <div className="mt-4 flex items-center gap-2">
            <button
              type="button"
              onClick={submit}
              disabled={busy === "save"}
              className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-4 py-1.5 text-xs text-emerald-200 transition hover:bg-emerald-500/20 disabled:opacity-50"
            >
              {busy === "save" ? "Сохранение…" : form.id ? "Сохранить" : "Добавить"}
            </button>
            <button
              type="button"
              onClick={() => setForm(null)}
              className="rounded-lg border border-neutral-700 px-4 py-1.5 text-xs text-neutral-300 transition hover:border-neutral-500"
            >
              Отмена
            </button>
          </div>
        </div>
      ) : null}

      <ul className="grid gap-3 sm:grid-cols-2 sm:gap-4">
        {items.map((search) => {
          const includeCount = parseInclude(includeToText(search.params)).length;
          const excludeCount = parseExclude(excludeToText(search.params)).length;
          const city = typeof search.params?.city === "string" ? search.params.city : "";
          const regionCount = parseExclude(listToText(search.params?.regions)).length;
          const excludeRegionCount = parseExclude(
            listToText(search.params?.exclude_regions),
          ).length;
          return (
            <li
              key={search.id}
              className="flex flex-col rounded-xl border border-neutral-800 bg-neutral-900/60 p-4 sm:p-5"
            >
              <div className="flex items-start justify-between gap-3">
                <Link href={`/searches/${search.id}`} className="min-w-0">
                  <p className="font-medium hover:underline">{search.name}</p>
                  <p className="mt-1 truncate text-xs text-neutral-500">{search.url}</p>
                </Link>
                <span
                  className={`whitespace-nowrap rounded-full border px-2 py-0.5 text-[10px] ${
                    search.is_active
                      ? "border-emerald-500/30 bg-emerald-500/15 text-emerald-300"
                      : "border-neutral-700 bg-neutral-800 text-neutral-400"
                  }`}
                >
                  {search.is_active ? "активен" : "на паузе"}
                </span>
              </div>
              <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-neutral-500">
                <span>cron: {search.schedule_cron}</span>
                <span>приоритет: {search.priority}</span>
                <span>страниц: {maxPagesOf(search.params) === "0" ? "∞" : maxPagesOf(search.params)}</span>
                <span>аккаунт: {accountName(search.account_id)}</span>
                {city ? <span>город: {city}</span> : null}
                {includeCount > 0 ? <span>включений: {includeCount}</span> : null}
                {excludeCount > 0 ? (
                  <span className="text-amber-300/80">стоп-слов: {excludeCount}</span>
                ) : null}
                {regionCount > 0 ? <span>городов: {regionCount}</span> : null}
                {excludeRegionCount > 0 ? (
                  <span className="text-sky-300/80">
                    исключено городов: {excludeRegionCount}
                  </span>
                ) : null}
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => crawl(search)}
                  disabled={busy === search.id}
                  className="rounded-lg border border-sky-500/40 bg-sky-500/10 px-3 py-1 text-xs text-sky-200 transition hover:bg-sky-500/20 disabled:opacity-50"
                >
                  Обход
                </button>
                <button
                  type="button"
                  onClick={() => openEdit(search)}
                  className="rounded-lg border border-neutral-700 px-3 py-1 text-xs text-neutral-300 transition hover:border-neutral-500"
                >
                  Изменить
                </button>
                <button
                  type="button"
                  onClick={() => toggleActive(search)}
                  disabled={busy === search.id}
                  className="rounded-lg border border-neutral-700 px-3 py-1 text-xs text-neutral-300 transition hover:border-neutral-500 disabled:opacity-50"
                >
                  {search.is_active ? "Пауза" : "Включить"}
                </button>
                <button
                  type="button"
                  onClick={() => remove(search)}
                  disabled={busy === search.id}
                  className="rounded-lg border border-red-500/30 px-3 py-1 text-xs text-red-300 transition hover:border-red-500/60 disabled:opacity-50"
                >
                  Удалить
                </button>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
