"use client";

import { useEffect, useState } from "react";

import { Modal } from "@/app/components/modal";
import { RegionPicker } from "@/app/components/region-picker";
import { useToast } from "@/app/components/toast";
import {
  type Account,
  type Search,
  createSearchClient,
  updateSearchClient,
} from "@/lib/api";
import { REGION_OPTIONS, regionName } from "@/lib/regions";

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

export function scheduleLabel(cron: string): string {
  const preset = SCHEDULE_PRESETS.find((item) => item.cron === cron);
  return preset ? preset.label : `свой график: ${cron}`;
}

export function parseInclude(text: string): string[][] {
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

export function parseExclude(text: string): string[] {
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

export function listFromParams(value: unknown): string[] {
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

export function maxPagesOf(params: Record<string, unknown> | null): string {
  const value = params?.max_pages;
  return typeof value === "number" ? String(value) : "5";
}

export function includeGroupsOf(params: Record<string, unknown> | null): string[][] {
  return parseInclude(includeToText(params));
}

export function excludeWordsOf(params: Record<string, unknown> | null): string[] {
  return parseExclude(excludeToText(params));
}

export function maxAgeOf(params: Record<string, unknown> | null): string {
  const value = params?.max_age_days;
  return typeof value === "number" ? String(value) : "0";
}

function formFromSearch(search: Search): FormState {
  const params = search.params;
  const city = typeof params?.city === "string" ? params.city : "";
  return {
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
  };
}

export function SearchFormModal({
  open,
  search,
  accounts,
  onClose,
  onSaved,
}: {
  open: boolean;
  search: Search | null;
  accounts: Account[];
  onClose: () => void;
  onSaved?: (search: Search) => void;
}) {
  const toast = useToast();
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) {
      return;
    }
    setForm(search ? formFromSearch(search) : { ...EMPTY_FORM });
  }, [open, search]);

  async function submit() {
    const name = form.name.trim();
    const url = form.url.trim();
    if (!name || !url) {
      toast.push("error", "Заполните название и ссылку на выдачу");
      return;
    }
    const params: Record<string, unknown> = {
      ...(search?.params ?? {}),
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
    setBusy(true);
    const result = form.id
      ? await updateSearchClient(form.id, payload)
      : await createSearchClient(payload);
    setBusy(false);
    if (!result.ok) {
      toast.push("error", result.error);
      return;
    }
    toast.push("success", form.id ? "Поиск обновлён" : "Поиск добавлен");
    onSaved?.(result.data);
    onClose();
  }

  const inputClass =
    "rounded-lg border border-neutral-800 bg-neutral-950 px-3 py-2 text-sm text-neutral-200 outline-none focus:border-sky-500/60";

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={form.id ? "Редактирование поиска" : "Новый поиск"}
      subtitle="Ссылка на выдачу, правила отбора, расписание и аккаунт"
      maxWidth="max-w-3xl"
      footer={
        <>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-neutral-700 px-4 py-1.5 text-xs text-neutral-300 transition hover:border-neutral-500"
          >
            Отмена
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={busy}
            className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-4 py-1.5 text-xs text-emerald-200 transition hover:bg-emerald-500/20 disabled:opacity-50"
          >
            {busy ? "Сохранение…" : form.id ? "Сохранить" : "Добавить"}
          </button>
        </>
      }
    >
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
          Аккаунт, от имени которого ищем
          <select
            value={form.accountId}
            onChange={(event) => setForm({ ...form, accountId: event.target.value })}
            className={inputClass}
          >
            <option value="">— основной —</option>
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
          Как часто обходить
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
            <option value="__custom__">своё расписание…</option>
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-neutral-400">
          Важность (приоритет)
          <input
            value={form.priority}
            onChange={(event) => setForm({ ...form, priority: event.target.value })}
            inputMode="numeric"
            className={inputClass}
          />
        </label>
        {form.customCron ? (
          <label className="flex flex-col gap-1 text-xs text-neutral-400 sm:col-span-2">
            Своё расписание (UTC): минуты часы день месяц день недели
            <input
              value={form.cron}
              onChange={(event) => setForm({ ...form, cron: event.target.value })}
              placeholder="0 */6 * * *"
              className={`${inputClass} font-mono text-xs`}
            />
          </label>
        ) : null}

        <label className="flex flex-col gap-1 text-xs text-neutral-400">
          Сколько страниц за один обход
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
          Учитывать только свежие, дней (0 = все)
          <input
            value={form.maxAgeDays}
            onChange={(event) => setForm({ ...form, maxAgeDays: event.target.value })}
            inputMode="numeric"
            placeholder="0"
            className={inputClass}
          />
          <span className="text-[10px] text-neutral-600">
            считаем датой появления тот день, когда мы впервые увидели объявление
          </span>
        </label>

        <label className="flex flex-col gap-1 text-xs text-neutral-400">
          Город, где искать
          <select
            value={form.city}
            onChange={(event) => setForm({ ...form, city: event.target.value })}
            className={inputClass}
          >
            <option value="">— как в ссылке —</option>
            {form.city && !REGION_OPTIONS.some((region) => region.slug === form.city) ? (
              <option value={form.city}>{regionName(form.city)} (текущий)</option>
            ) : null}
            {REGION_OPTIONS.map((region) => (
              <option key={region.slug} value={region.slug}>
                {region.name}
              </option>
            ))}
          </select>
        </label>
        <div className="flex flex-col gap-1 text-xs text-neutral-400">
          Учитывать только эти города
          <RegionPicker
            value={form.regions}
            onChange={(next) => setForm({ ...form, regions: next })}
            emptyLabel="Все города"
          />
          <span className="text-[10px] text-neutral-600">
            пусто — все города; отметить нужные галочками
          </span>
        </div>
        <div className="flex flex-col gap-1 text-xs text-neutral-400 sm:col-span-2">
          Не учитывать эти города
          <RegionPicker
            value={form.excludeRegions}
            onChange={(next) => setForm({ ...form, excludeRegions: next })}
            emptyLabel="Никого не исключаем"
          />
          <span className="text-[10px] text-neutral-600">
            объявления из этих городов останутся в списке, но не пойдут в расчёты
          </span>
        </div>

        <label className="flex flex-col gap-1 text-xs text-neutral-400">
          В названии обязательно (строка — одно условие, варианты через запятую)
          <textarea
            value={form.include}
            onChange={(event) => setForm({ ...form, include: event.target.value })}
            rows={3}
            placeholder={"devialet\ndione, dion"}
            className={inputClass}
          />
          <span className="text-[10px] text-neutral-600">
            пример: «devialet» и («dione» или «dion») — подходят только такие объявления
          </span>
        </label>
        <label className="flex flex-col gap-1 text-xs text-neutral-400">
          Не учитывать, если в названии есть (через запятую)
          <textarea
            value={form.exclude}
            onChange={(event) => setForm({ ...form, exclude: event.target.value })}
            rows={3}
            placeholder="чехол, копия, реплика, ремонт"
            className={inputClass}
          />
          <span className="text-[10px] text-neutral-600">
            такие объявления останутся в списке с пометкой, но не попадут в цены
          </span>
        </label>
      </div>
    </Modal>
  );
}
