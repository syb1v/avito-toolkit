"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { InfoHint } from "@/app/components/info-hint";
import { Modal } from "@/app/components/modal";
import { RegionPicker } from "@/app/components/region-picker";
import { useConfirm } from "@/app/components/confirm";
import { useToast } from "@/app/components/toast";
import {
  type Account,
  type Search,
  createSearchClient,
  deleteSearchClient,
  fetchSearches,
  triggerCrawl,
  updateSearchClient,
} from "@/lib/api";
import { REGIONS, regionName } from "@/lib/regions";

type FormState = {
  id: string | null;
  name: string;
  url: string;
  cron: string;
  customCron: boolean;
  priority: string;
  maxPages: string;
  maxAgeDays: string;
  include: string;
  exclude: string;
  city: string;
  regions: string[];
  excludeRegions: string[];
  accountId: string;
};

const EMPTY_FORM: FormState = {
  id: null,
  name: "",
  url: "",
  cron: "0 */6 * * *",
  customCron: false,
  priority: "100",
  maxPages: "5",
  maxAgeDays: "0",
  include: "",
  exclude: "",
  city: "",
  regions: [],
  excludeRegions: [],
  accountId: "",
};

const SCHEDULE_PRESETS = [
  { cron: "*/15 * * * *", label: "каждые 15 минут" },
  { cron: "*/30 * * * *", label: "каждые 30 минут" },
  { cron: "0 * * * *", label: "каждый час" },
  { cron: "0 */3 * * *", label: "каждые 3 часа" },
  { cron: "0 */6 * * *", label: "каждые 6 часов" },
  { cron: "0 */12 * * *", label: "каждые 12 часов" },
  { cron: "0 6 * * *", label: "раз в день (09:00 МСК)" },
  { cron: "0 6 * * 1", label: "раз в неделю (понедельник)" },
];

const PAGE_OPTIONS = [
  { value: "1", label: "1 страница (~50 лотов)" },
  { value: "3", label: "3 страницы (~150 лотов)" },
  { value: "5", label: "5 страниц (~250 лотов)" },
  { value: "10", label: "10 страниц (~500 лотов)" },
  { value: "20", label: "20 страниц (~1000 лотов)" },
  { value: "0", label: "Без лимита (до конца выдачи)" },
];

function scheduleLabel(cron: string): string {
  const preset = SCHEDULE_PRESETS.find((item) => item.cron === cron);
  return preset ? preset.label : `свой cron: ${cron}`;
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

function listFromParams(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map(String).filter(Boolean);
  }
  if (typeof value === "string") {
    return value
      .split(/[\n,;]+/)
      .map((chunk) => chunk.trim())
      .filter(Boolean);
  }
  return [];
}

function maxPagesOf(params: Record<string, unknown> | null): string {
  const value = params?.max_pages;
  return typeof value === "number" ? String(value) : "5";
}

function maxAgeOf(params: Record<string, unknown> | null): string {
  const value = params?.max_age_days;
  return typeof value === "number" ? String(value) : "0";
}

export function SearchManager({
  initial,
  accounts,
  editId,
}: {
  initial: Search[];
  accounts: Account[];
  editId?: string | null;
}) {
  const router = useRouter();
  const toast = useToast();
  const confirm = useConfirm();
  const [items, setItems] = useState(initial);
  const [form, setForm] = useState<FormState | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const accountName = (id: string | null) =>
    accounts.find((account) => account.id === id)?.name ?? "—";

  async function refresh() {
    setItems(await fetchSearches());
    router.refresh();
  }

  function openCreate() {
    setForm({ ...EMPTY_FORM, accountId: accounts[0]?.id ?? "" });
  }

  function openEdit(search: Search) {
    const params = search.params;
    const city = typeof params?.city === "string" ? params.city : "";
    setForm({
      id: search.id,
      name: search.name,
      url: search.url,
      cron: search.schedule_cron,
      customCron: !SCHEDULE_PRESETS.some((preset) => preset.cron === search.schedule_cron),
      priority: String(search.priority),
      maxPages: maxPagesOf(params),
      maxAgeDays: maxAgeOf(params),
      include: includeToText(params),
      exclude: excludeToText(params),
      city,
      regions: listFromParams(params?.regions),
      excludeRegions: listFromParams(params?.exclude_regions),
      accountId: search.account_id ?? "",
    });
  }

  useEffect(() => {
    if (!editId) {
      return;
    }
    const search = initial.find((item) => item.id === editId);
    if (search) {
      openEdit(search);
      router.replace("/", { scroll: false });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editId]);

  async function submit() {
    if (!form) {
      return;
    }
    const name = form.name.trim();
    const url = form.url.trim();
    if (!name || !url) {
      toast.push("error", "Заполните название и ссылку на выдачу");
      return;
    }
    const current = items.find((item) => item.id === form.id);
    const params: Record<string, unknown> = {
      ...(current?.params ?? {}),
      keyword_groups: parseInclude(form.include),
      exclude_keywords: parseExclude(form.exclude),
      max_pages: Math.max(0, Number(form.maxPages) || 0),
      max_age_days: Math.max(0, Number(form.maxAgeDays) || 0),
      city: form.city,
      regions: form.regions,
      exclude_regions: form.excludeRegions,
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
      toast.push("error", result.error);
      return;
    }
    setForm(null);
    toast.push("success", form.id ? "Поиск обновлён" : "Поиск добавлен");
    await refresh();
  }

  async function toggleActive(search: Search) {
    setBusy(search.id);
    const result = await updateSearchClient(search.id, { is_active: !search.is_active });
    setBusy(null);
    if (!result.ok) {
      toast.push("error", result.error);
      return;
    }
    toast.push("info", search.is_active ? `«${search.name}» на паузе` : `«${search.name}» включён`);
    await refresh();
  }

  async function remove(search: Search) {
    const ok = await confirm({
      title: "Удалить поиск?",
      text: `«${search.name}» и вся собранная выдача будут удалены. Действие необратимо.`,
      confirmLabel: "Удалить",
      danger: true,
    });
    if (!ok) {
      return;
    }
    setBusy(search.id);
    const result = await deleteSearchClient(search.id);
    setBusy(null);
    if (!result.ok) {
      toast.push("error", result.error);
      return;
    }
    toast.push("success", `Поиск «${search.name}» удалён`);
    await refresh();
  }

  async function crawl(search: Search) {
    setBusy(search.id);
    const ok = await triggerCrawl(search.id);
    setBusy(null);
    if (ok) {
      toast.push("info", `Обход «${search.name}» поставлен в очередь`);
    } else {
      toast.push("error", "Не удалось запустить обход");
    }
  }

  const inputClass =
    "rounded-lg border border-neutral-800 bg-neutral-950 px-3 py-2 text-sm text-neutral-200 outline-none focus:border-sky-500/60";

  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center">
          <h2 className="text-lg font-medium">Поиски</h2>
          <InfoHint
            title="Как управлять поисками"
            text="Поиск — это URL выдачи Авито и фильтры. Включение (include) — все строки-группы должны совпасть (AND), альтернативы в строке через запятую (OR). Исключение (exclude) — любое из стоп-слов убирает объявление из статистики. Страницы: лимит обхода (0 = без лимита). Свежесть: учитывать только объявления, впервые увиденные за последние N дней. Города: «Город выдачи» меняет регион в URL, «Города: только/исключить» фильтруют по региону объявления."
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

      <Modal
        open={form !== null}
        onClose={() => setForm(null)}
        title={form?.id ? "Редактирование поиска" : "Новый поиск"}
        subtitle="URL выдачи, фильтры, расписание и аккаунт"
        maxWidth="max-w-3xl"
        footer={
          <>
            <button
              type="button"
              onClick={() => setForm(null)}
              className="rounded-lg border border-neutral-700 px-4 py-1.5 text-xs text-neutral-300 transition hover:border-neutral-500"
            >
              Отмена
            </button>
            <button
              type="button"
              onClick={submit}
              disabled={busy === "save"}
              className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-4 py-1.5 text-xs text-emerald-200 transition hover:bg-emerald-500/20 disabled:opacity-50"
            >
              {busy === "save" ? "Сохранение…" : form?.id ? "Сохранить" : "Добавить"}
            </button>
          </>
        }
      >
        {form ? (
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="flex flex-col gap-1 text-xs text-neutral-400">
              Название
              <input
                value={form.name}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
                placeholder="Devialet Dione"
                className={inputClass}
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-neutral-400">
              Аккаунт (поисковик)
              <select
                value={form.accountId}
                onChange={(event) => setForm({ ...form, accountId: event.target.value })}
                className={inputClass}
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
                className={`${inputClass} font-mono text-xs`}
              />
            </label>

            <label className="flex flex-col gap-1 text-xs text-neutral-400">
              Расписание
              <select
                value={form.customCron ? "__custom__" : form.cron}
                onChange={(event) => {
                  const value = event.target.value;
                  if (value === "__custom__") {
                    setForm({ ...form, customCron: true });
                  } else {
                    setForm({ ...form, cron: value, customCron: false });
                  }
                }}
                className={inputClass}
              >
                {SCHEDULE_PRESETS.map((preset) => (
                  <option key={preset.cron} value={preset.cron}>
                    {preset.label}
                  </option>
                ))}
                <option value="__custom__">свой cron…</option>
              </select>
            </label>
            <label className="flex flex-col gap-1 text-xs text-neutral-400">
              Приоритет
              <input
                value={form.priority}
                onChange={(event) => setForm({ ...form, priority: event.target.value })}
                inputMode="numeric"
                className={inputClass}
              />
            </label>
            {form.customCron ? (
              <label className="flex flex-col gap-1 text-xs text-neutral-400 sm:col-span-2">
                Cron (UTC): минуты часы день месяц день_недели
                <input
                  value={form.cron}
                  onChange={(event) => setForm({ ...form, cron: event.target.value })}
                  placeholder="0 */6 * * *"
                  className={`${inputClass} font-mono text-xs`}
                />
              </label>
            ) : null}

            <label className="flex flex-col gap-1 text-xs text-neutral-400">
              Страниц за обход
              <select
                value={form.maxPages}
                onChange={(event) => setForm({ ...form, maxPages: event.target.value })}
                className={inputClass}
              >
                {PAGE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-xs text-neutral-400">
              Свежесть, дней (0 = все)
              <input
                value={form.maxAgeDays}
                onChange={(event) => setForm({ ...form, maxAgeDays: event.target.value })}
                inputMode="numeric"
                placeholder="0"
                className={inputClass}
              />
              <span className="text-[10px] text-neutral-600">
                только объявления, впервые увиденные за последние N дней
              </span>
            </label>

            <label className="flex flex-col gap-1 text-xs text-neutral-400">
              Город выдачи
              <select
                value={form.city}
                onChange={(event) => setForm({ ...form, city: event.target.value })}
                className={inputClass}
              >
                <option value="">— как в ссылке —</option>
                {form.city && !REGIONS.some((region) => region.slug === form.city) ? (
                  <option value={form.city}>{form.city} (текущий)</option>
                ) : null}
                {REGIONS.map((region) => (
                  <option key={region.slug} value={region.slug}>
                    {region.name}
                  </option>
                ))}
              </select>
            </label>
            <div className="flex flex-col gap-1 text-xs text-neutral-400">
              Города: только эти
              <RegionPicker
                value={form.regions}
                onChange={(next) => setForm({ ...form, regions: next })}
                emptyLabel="Все города"
              />
              <span className="text-[10px] text-neutral-600">
                пусто = все города; несколько — отметить галочками
              </span>
            </div>
            <div className="flex flex-col gap-1 text-xs text-neutral-400 sm:col-span-2">
              Исключить города
              <RegionPicker
                value={form.excludeRegions}
                onChange={(next) => setForm({ ...form, excludeRegions: next })}
                emptyLabel="Ничего не исключаем"
              />
              <span className="text-[10px] text-neutral-600">
                лоты этих городов останутся в выдаче, но вне расчёта
              </span>
            </div>

            <label className="flex flex-col gap-1 text-xs text-neutral-400">
              Включение (строка = AND-группа, альтернативы через запятую)
              <textarea
                value={form.include}
                onChange={(event) => setForm({ ...form, include: event.target.value })}
                rows={3}
                placeholder={"devialet\ndione, dion"}
                className={inputClass}
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-neutral-400">
              Исключение (стоп-слова через запятую)
              <textarea
                value={form.exclude}
                onChange={(event) => setForm({ ...form, exclude: event.target.value })}
                rows={3}
                placeholder="чехол, копия, реплика, ремонт"
                className={inputClass}
              />
            </label>
          </div>
        ) : null}
      </Modal>

      <ul className="grid gap-3 sm:grid-cols-2 sm:gap-4">
        {items.map((search) => {
          const includeCount = parseInclude(includeToText(search.params)).length;
          const excludeCount = parseExclude(excludeToText(search.params)).length;
          const city = typeof search.params?.city === "string" ? search.params.city : "";
          const regionCount = listFromParams(search.params?.regions).length;
          const excludeRegionCount = listFromParams(search.params?.exclude_regions).length;
          const ageDays = Number(maxAgeOf(search.params)) || 0;
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
                <span>расписание: {scheduleLabel(search.schedule_cron)}</span>
                <span>приоритет: {search.priority}</span>
                <span>
                  страниц: {maxPagesOf(search.params) === "0" ? "∞" : maxPagesOf(search.params)}
                </span>
                {ageDays > 0 ? <span>свежесть: {ageDays} дн.</span> : null}
                <span>аккаунт: {accountName(search.account_id)}</span>
                {city ? <span>город: {regionName(city)}</span> : null}
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
