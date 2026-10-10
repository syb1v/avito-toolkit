"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { Modal } from "@/app/components/modal";
import { useConfirm } from "@/app/components/confirm";
import { useToast } from "@/app/components/toast";
import {
  applyImportFileClient,
  fetchImportAccountsClient,
  generateImportFiltersClient,
  importFromAccountClient,
  uploadImportFile,
  type Account,
  type ImportAccountOption,
  type ImportFileResult,
  type ImportFilter,
  type ImportFileRow,
} from "@/lib/api";
import { formatPrice } from "@/lib/format";
import { RegionPicker } from "@/app/components/region-picker";

const PAGE_SIZE = 20;
const BATCH = 20;

function usableRow(row: ImportFileRow): row is ImportFileRow & { avito_id: number; price: number } {
  return row.avito_id !== null && row.price !== null && row.price > 0;
}

function includeText(filter: ImportFilter, edit?: string): string {
  if (edit !== undefined) {
    return edit;
  }
  return filter.keyword_groups.map((group) => group.join(", ")).join(" | ");
}

function excludeText(filter: ImportFilter, edit?: string): string {
  return edit ?? filter.exclude_keywords.join(", ");
}

function parseInclude(value: string): string[][] {
  return value
    .split("|")
    .map((group) =>
      group
        .split(",")
        .map((word) => word.trim())
        .filter(Boolean),
    )
    .filter((group) => group.length > 0);
}

function parseExclude(value: string): string[] {
  return value
    .split(",")
    .map((word) => word.trim())
    .filter(Boolean);
}

export function ImportSearchesModal({ accounts }: { accounts: Account[] }) {
  const [open, setOpen] = useState(false);
  const [parsed, setParsed] = useState<ImportFileResult | null>(null);
  const [fileBusy, setFileBusy] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [filters, setFilters] = useState<Record<number, ImportFilter>>({});
  const [edits, setEdits] = useState<Record<number, { query?: string; include?: string; exclude?: string }>>({});
  const [page, setPage] = useState(0);
  const [aiBusy, setAiBusy] = useState(false);
  const [applyBusy, setApplyBusy] = useState(false);
  const [accountId, setAccountId] = useState("");
  const [source, setSource] = useState<"file" | "api">("file");
  const [apiAccounts, setApiAccounts] = useState<ImportAccountOption[]>([]);
  const [apiAccountId, setApiAccountId] = useState("");
  const [apiBusy, setApiBusy] = useState(false);
  const [regions, setRegions] = useState<string[]>([]);
  const [excludeRegions, setExcludeRegions] = useState<string[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();
  const toast = useToast();
  const confirm = useConfirm();

  useEffect(() => {
    if (!open) {
      return;
    }
    fetchImportAccountsClient().then((accounts) => {
      if (accounts) {
        setApiAccounts(accounts);
      }
    });
  }, [open]);

  const rows = useMemo(() => parsed?.rows ?? [], [parsed]);
  const usable = useMemo(() => rows.filter(usableRow), [rows]);
  const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  const pageRows = rows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const selectedRows = usable.filter((row) => selected.has(row.avito_id));

  function reset() {
    setParsed(null);
    setSelected(new Set());
    setFilters({});
    setEdits({});
    setPage(0);
  }

  async function onFile(file: File) {
    setFileBusy(true);
    const result = await uploadImportFile(file);
    setFileBusy(false);
    if ("error" in result) {
      toast.push("error", result.error);
      return;
    }
    setParsed(result);
    setSelected(new Set());
    setFilters({});
    setEdits({});
    setPage(0);
    toast.push("info", `Файл разобран: ${result.total} объявлений`);
  }

  function toggle(row: ImportFileRow & { avito_id: number; price: number }) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(row.avito_id)) {
        next.delete(row.avito_id);
      } else {
        next.add(row.avito_id);
      }
      return next;
    });
  }

  function chunk<T>(items: T[], size: number): T[][] {
    const chunks: T[][] = [];
    for (let index = 0; index < items.length; index += size) {
      chunks.push(items.slice(index, index + size));
    }
    return chunks;
  }

  async function generateFilters(ids: number[]) {
    if (!parsed || ids.length === 0) {
      return [];
    }
    setAiBusy(true);
    const merged = { ...filters };
    let generated = 0;
    for (const part of chunk(ids, BATCH)) {
      const result = await generateImportFiltersClient(parsed.token, part);
      if (!result.ok) {
        toast.push("error", result.error);
        break;
      }
      for (const item of result.data.items) {
        merged[item.avito_id] = item;
        if (item.generated) {
          generated += 1;
        }
      }
    }
    setAiBusy(false);
    setFilters(merged);
    if (generated > 0) {
      toast.push("success", `AI-фильтры готовы для ${generated} товаров — проверьте и поправьте`);
    } else {
      toast.push("info", "AI недоступен — подставлены простые фильтры, можно поправить руками");
    }
    return merged;
  }

  async function apply() {
    if (!parsed || selectedRows.length === 0) {
      return;
    }
    setApplyBusy(true);
    const missing = selectedRows.filter((row) => !filters[row.avito_id]);
    const fresh = missing.length > 0 ? await generateFilters(missing.map((row) => row.avito_id)) : filters;
    const ok = await confirm({
      title: `Создать поиски: ${selectedRows.length}?`,
      text:
        selectedRows.length > 20
          ? `Будет создано ${selectedRows.length} поисков и столько же SKU. Обходы распределятся по минутам и часам, но учтите лимит аккаунта (~80 стр./день) — за разумное время обойдутся не все сразу.`
          : `Будет создано ${selectedRows.length} поисков (cron раз в сутки) и столько же позиций в «Наши объявления». AI-фильтры применятся как показано в таблице.`,
      confirmLabel: "Создать",
    });
    if (!ok) {
      setApplyBusy(false);
      return;
    }
    const items = selectedRows.map((row) => {
      const filter = fresh[row.avito_id];
      const edit = edits[row.avito_id] ?? {};
      return {
        avito_id: row.avito_id,
        title: row.title,
        price: row.price,
        status: row.status,
        query: edit.query ?? filter?.query ?? row.title.slice(0, 80),
        keyword_groups: parseInclude(includeText(filter!, edit.include) || row.title.slice(0, 80)),
        exclude_keywords: parseExclude(excludeText(filter!, edit.exclude)),
      };
    });
    const totals = { searches: 0, created: 0, updated: 0, matched: 0, skipped: 0 };
    let failed = 0;
    for (const part of chunk(items, BATCH)) {
      const result = await applyImportFileClient(parsed.token, {
        items: part,
        account_id: accountId || null,
        regions,
        exclude_regions: excludeRegions,
      });
      if (!result.ok) {
        failed += part.length;
        continue;
      }
      totals.searches += result.data.created_searches;
      totals.created += result.data.created_listings;
      totals.updated += result.data.updated_listings;
      totals.matched += result.data.matched;
      totals.skipped += result.data.skipped;
    }
    setApplyBusy(false);
    toast.push(
      failed > 0 ? "info" : "success",
      `Поисков: ${totals.searches} (дублей: ${totals.skipped}), SKU: +${totals.created}/${totals.updated}, матчей: ${totals.matched}${failed > 0 ? `, ошибок: ${failed}` : ""}`,
    );
    setOpen(false);
    reset();
    router.refresh();
  }

  const searcherAccounts = accounts.filter((account) => account.role !== "seller");

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="rounded-lg border border-neutral-700 px-3 py-1.5 text-xs text-neutral-300 transition hover:border-neutral-500"
      >
        Импорт из файла
      </button>
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="Импорт поисков из выгрузки Авито"
        subtitle="xlsx из кабинета: Id, Title, Price, AvitoStatus, Category"
        maxWidth="max-w-5xl"
        footer={
          <>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="rounded-lg border border-neutral-700 px-4 py-1.5 text-xs text-neutral-300 transition hover:border-neutral-500"
            >
              Закрыть
            </button>
            {parsed ? (
              <>
                <button
                  type="button"
                  disabled={aiBusy || selected.size === 0}
                  onClick={() => generateFilters([...selected])}
                  className="rounded-lg border border-violet-500/40 bg-violet-500/10 px-4 py-1.5 text-xs text-violet-200 transition hover:bg-violet-500/20 disabled:opacity-50"
                >
                  {aiBusy ? "AI думает…" : `Сгенерировать фильтры (${selected.size})`}
                </button>
                <button
                  type="button"
                  disabled={applyBusy || selected.size === 0}
                  onClick={apply}
                  className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-4 py-1.5 text-xs text-emerald-200 transition hover:bg-emerald-500/20 disabled:opacity-50"
                >
                  {applyBusy ? "Создаём…" : `Создать поиски (${selected.size})`}
                </button>
              </>
            ) : null}
          </>
        }
      >
        {parsed === null ? (
          <div className="flex flex-col gap-3">
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setSource("file")}
                className={`flex-1 rounded-lg border px-3 py-2 text-xs transition ${
                  source === "file"
                    ? "border-sky-500/40 bg-sky-500/10 text-sky-200"
                    : "border-neutral-800 text-neutral-400 hover:border-neutral-600"
                }`}
              >
                Из файла xlsx
              </button>
              <button
                type="button"
                onClick={() => setSource("api")}
                className={`flex-1 rounded-lg border px-3 py-2 text-xs transition ${
                  source === "api"
                    ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-200"
                    : "border-neutral-800 text-neutral-400 hover:border-neutral-600"
                }`}
              >
                Из API-аккаунтов
              </button>
            </div>
            {source === "file" ? (
              <>
                <p className="text-sm text-neutral-400">
                  Загрузите xlsx-выгрузку своих объявлений из кабинета Авито. Мы разберём
                  файл, предложим AI-фильтры (что обязательно в названии, что исключать —
                  цвета, другие модели), вы отметите товары и создадите поиски.
                </p>
                <input
                  ref={inputRef}
                  type="file"
                  accept=".xlsx"
                  className="hidden"
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (file) {
                      onFile(file);
                    }
                    event.target.value = "";
                  }}
                />
                <button
                  type="button"
                  disabled={fileBusy}
                  onClick={() => inputRef.current?.click()}
                  className="self-start rounded-lg border border-sky-500/40 bg-sky-500/10 px-4 py-2 text-sm text-sky-200 transition hover:bg-sky-500/20 disabled:opacity-50"
                >
                  {fileBusy ? "Разбираю файл…" : "Выбрать xlsx"}
                </button>
              </>
            ) : (
              <>
                <p className="text-sm text-neutral-400">
                  Товары берутся из «Наших объявлений» API-аккаунтов (те, что уже
                  импортированы из файла один раз). Дальше — как обычно: AI-фильтры,
                  выбор и создание поисков.
                </p>
                {apiAccounts.length === 0 ? (
                  <p className="text-xs text-amber-300/80">
                    API-аккаунтов нет — добавьте аккаунт продавца по ключу в блоке «Аккаунты».
                  </p>
                ) : (
                  <>
                    <label className="flex items-center gap-2 text-xs text-neutral-400">
                      Аккаунт
                      <select
                        value={apiAccountId}
                        onChange={(event) => setApiAccountId(event.target.value)}
                        className="rounded-lg border border-neutral-800 bg-neutral-950 px-2 py-1.5 text-xs text-neutral-200 outline-none focus:border-sky-500/60"
                      >
                        <option value="">
                          Все API-аккаунты (
                          {apiAccounts.reduce((sum, item) => sum + item.items_count, 0)})
                        </option>
                        {apiAccounts.map((item) => (
                          <option key={item.id} value={item.id}>
                            {item.name} ({item.items_count})
                          </option>
                        ))}
                      </select>
                    </label>
                    <button
                      type="button"
                      disabled={apiBusy}
                      onClick={async () => {
                        setApiBusy(true);
                        const result = await importFromAccountClient(apiAccountId || null);
                        setApiBusy(false);
                        if ("error" in result) {
                          toast.push("error", result.error);
                          return;
                        }
                        setParsed(result);
                        setSelected(new Set());
                        setFilters({});
                        setEdits({});
                        setPage(0);
                        toast.push("info", `Товаров загружено: ${result.total}`);
                      }}
                      className="self-start rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-4 py-2 text-sm text-emerald-200 transition hover:bg-emerald-500/20 disabled:opacity-50"
                    >
                      {apiBusy ? "Загружаю…" : "Загрузить товары"}
                    </button>
                  </>
                )}
              </>
            )}
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-neutral-400">
              <span>
                Всего строк: {parsed.total} · выбрано {selected.size}
              </span>
              <div className="flex flex-wrap items-center gap-3">
                <div className="flex items-center gap-2">
                  <span>Регионы</span>
                  <RegionPicker
                    value={regions}
                    onChange={setRegions}
                    emptyLabel="Вся Россия"
                  />
                </div>
                <div className="flex items-center gap-2">
                  <span>Исключить</span>
                  <RegionPicker
                    value={excludeRegions}
                    onChange={setExcludeRegions}
                    emptyLabel="Ничего"
                  />
                </div>
                <label className="flex items-center gap-2">
                  Аккаунт для обходов
                  <select
                    value={accountId}
                    onChange={(event) => setAccountId(event.target.value)}
                    className="rounded-lg border border-neutral-800 bg-neutral-950 px-2 py-1 text-xs text-neutral-200 outline-none focus:border-sky-500/60"
                  >
                     <option value="">— выберите поисковик —</option>
                    {searcherAccounts.map((account) => (
                      <option key={account.id} value={account.id}>
                        {account.name}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            </div>

            <div className="overflow-x-auto rounded-lg border border-neutral-800">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-neutral-800 text-left text-xs uppercase tracking-wider text-neutral-500">
                    <th className="px-3 py-2 font-medium">
                      <input
                        type="checkbox"
                        title="Выбрать страницу"
                        aria-label="Выбрать страницу"
                        checked={
                          pageRows.filter(usableRow).length > 0 &&
                          pageRows
                            .filter(usableRow)
                            .every((row) => selected.has(row.avito_id))
                        }
                        onChange={(event) => {
                          const ids = pageRows.filter(usableRow).map((row) => row.avito_id);
                          setSelected((current) => {
                            const next = new Set(current);
                            for (const id of ids) {
                              if (event.target.checked) {
                                next.add(id);
                              } else {
                                next.delete(id);
                              }
                            }
                            return next;
                          });
                        }}
                      />
                    </th>
                    <th className="px-3 py-2 font-medium">Товар</th>
                    <th className="px-3 py-2 text-right font-medium">Цена</th>
                    <th className="px-3 py-2 font-medium">Статус</th>
                    <th className="px-3 py-2 font-medium">Фильтры для поиска</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-neutral-800">
                  {pageRows.map((row, index) => {
                    const rowId = row.avito_id ?? `row-${page * PAGE_SIZE + index}`;
                    const selectable = usableRow(row);
                    const filter = row.avito_id !== null ? filters[row.avito_id] : undefined;
                    const edit = row.avito_id !== null ? edits[row.avito_id] : undefined;
                    return (
                      <tr key={rowId} className="align-top">
                        <td className="px-3 py-2">
                          <input
                            type="checkbox"
                            disabled={!selectable}
                            checked={row.avito_id !== null && selected.has(row.avito_id)}
                            onChange={() => selectable && toggle(row)}
                            aria-label={`Выбрать: ${row.title.slice(0, 60)}`}
                          />
                        </td>
                        <td className="max-w-xs px-3 py-2">
                          <p className="line-clamp-2" title={row.title}>
                            {row.title}
                          </p>
                          <p className="text-xs text-neutral-600">
                            {row.category ?? ""}
                            {row.avito_id ? ` · ${row.avito_id}` : ""}
                          </p>
                        </td>
                        <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums">
                          {row.price !== null ? formatPrice(row.price) : "—"}
                        </td>
                        <td className="whitespace-nowrap px-3 py-2 text-xs text-neutral-400">
                          {row.status ?? "—"}
                        </td>
                        <td className="min-w-[320px] px-3 py-2">
                          {filter ? (
                            <div className="flex flex-col gap-1">
                              <input
                                value={edit?.query ?? filter.query}
                                onChange={(event) =>
                                  row.avito_id !== null &&
                                  setEdits((current) => ({
                                    ...current,
                                    [row.avito_id as number]: {
                                      ...current[row.avito_id as number],
                                      query: event.target.value,
                                    },
                                  }))
                                }
                                className="rounded border border-neutral-800 bg-neutral-950 px-2 py-1 text-xs text-neutral-200 outline-none focus:border-sky-500/60"
                                placeholder="запрос"
                              />
                              <input
                                value={includeText(filter, edit?.include)}
                                onChange={(event) =>
                                  row.avito_id !== null &&
                                  setEdits((current) => ({
                                    ...current,
                                    [row.avito_id as number]: {
                                      ...current[row.avito_id as number],
                                      include: event.target.value,
                                    },
                                  }))
                                }
                                className="rounded border border-neutral-800 bg-neutral-950 px-2 py-1 text-xs text-emerald-200/90 outline-none focus:border-sky-500/60"
                                placeholder="обязательно: бренд, модель (варианты через запятую, группы через |)"
                              />
                              <input
                                value={excludeText(filter, edit?.exclude)}
                                onChange={(event) =>
                                  row.avito_id !== null &&
                                  setEdits((current) => ({
                                    ...current,
                                    [row.avito_id as number]: {
                                      ...current[row.avito_id as number],
                                      exclude: event.target.value,
                                    },
                                  }))
                                }
                                className="rounded border border-neutral-800 bg-neutral-950 px-2 py-1 text-xs text-red-300/80 outline-none focus:border-sky-500/60"
                                placeholder="исключать: цвета, чужие модели, мусор"
                              />
                              {!filter.generated ? (
                                <span className="text-[11px] text-amber-300/80">
                                  без AI (fallback) — проверьте руками
                                </span>
                              ) : null}
                              {filter.generated && filter.research_status === "needs_review" ? (
                                <span className="text-[11px] text-amber-300/80">
                                  модель требует проверки источниками
                                </span>
                              ) : null}
                            </div>
                          ) : (
                            <span className="text-xs text-neutral-600">
                              выберите товар и нажмите «Сгенерировать фильтры»
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-neutral-400">
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setPage((value) => Math.max(0, value - 1))}
                  disabled={page === 0}
                  className="rounded border border-neutral-700 px-2 py-1 disabled:opacity-40"
                >
                  ←
                </button>
                <span>
                  стр. {page + 1} из {pages}
                </span>
                <button
                  type="button"
                  onClick={() => setPage((value) => Math.min(pages - 1, value + 1))}
                  disabled={page >= pages - 1}
                  className="rounded border border-neutral-700 px-2 py-1 disabled:opacity-40"
                >
                  →
                </button>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-neutral-500">
                  выбрано {selected.size} из {usable.length}
                </span>
                <button
                  type="button"
                  onClick={() => setSelected(new Set(usable.map((row) => row.avito_id)))}
                  className="rounded border border-neutral-700 px-2 py-1 hover:border-neutral-500"
                >
                  Выбрать всё
                </button>
                <button
                  type="button"
                  onClick={() => {
                    const ids = pageRows.filter(usableRow).map((row) => row.avito_id);
                    setSelected(new Set(ids));
                  }}
                  className="rounded border border-neutral-700 px-2 py-1 hover:border-neutral-500"
                >
                  Только страницу
                </button>
                <button
                  type="button"
                  onClick={() => setSelected(new Set())}
                  disabled={selected.size === 0}
                  className="rounded border border-neutral-700 px-2 py-1 hover:border-neutral-500 disabled:opacity-40"
                >
                  Снять выделение
                </button>
              </div>
            </div>
          </div>
        )}
      </Modal>
    </>
  );
}
