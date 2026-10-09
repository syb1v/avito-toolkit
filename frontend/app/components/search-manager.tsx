"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useConfirm } from "@/app/components/confirm";
import { ImportSearchesModal } from "@/app/components/import-searches-modal";
import { InfoHint } from "@/app/components/info-hint";
import {
  SearchFormModal,
  excludeWordsOf,
  includeGroupsOf,
  listFromParams,
  maxAgeOf,
  maxPagesOf,
  scheduleLabel,
} from "@/app/components/search-form-modal";
import { useToast } from "@/app/components/toast";
import {
  type Account,
  type Search,
  deleteSearchClient,
  fetchSearches,
  triggerCrawl,
  updateSearchClient,
} from "@/lib/api";
import { regionName } from "@/lib/regions";

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
  const [target, setTarget] = useState<{ search: Search | null } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const accountName = (id: string | null) =>
    accounts.find((account) => account.id === id)?.name ?? "—";

  async function refresh() {
    setItems(await fetchSearches());
    router.refresh();
  }

  useEffect(() => {
    if (!editId) {
      return;
    }
    const search = initial.find((item) => item.id === editId);
    if (search) {
      setTarget({ search });
      router.replace("/", { scroll: false });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editId]);

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

  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center">
          <h2 className="text-lg font-medium">Поиски</h2>
          <InfoHint
            title="Что такое поиск"
            text="Поиск — это ссылка на выдачу Авито и правила, что считать вашим товаром. «В названии обязательно» — слова, которые должны быть (каждая строка обязательна, варианты — через запятую). «Не учитывать» — слова-исключения. Страницы — сколько пролистать за один раз. Свежесть — брать только недавно появившиеся объявления. Города — где искать и какие города не учитывать."
          />
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-neutral-500">{items.length} шт.</span>
          <ImportSearchesModal accounts={accounts} />
          <button
            type="button"
            onClick={() => setTarget({ search: null })}
            className="rounded-lg border border-sky-500/40 bg-sky-500/10 px-3 py-1.5 text-xs text-sky-200 transition hover:bg-sky-500/20"
          >
            + Добавить поиск
          </button>
        </div>
      </div>

      <SearchFormModal
        open={target !== null}
        search={target?.search ?? null}
        accounts={accounts}
        onClose={() => setTarget(null)}
        onSaved={refresh}
      />

      <ul className="grid gap-3 sm:grid-cols-2 sm:gap-4">
        {items.map((search) => {
          const includeCount = includeGroupsOf(search.params).length;
          const excludeCount = excludeWordsOf(search.params).length;
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
                <span>обход: {scheduleLabel(search.schedule_cron)}</span>
                <span>
                  страниц: {maxPagesOf(search.params) === "0" ? "все" : maxPagesOf(search.params)}
                </span>
                {ageDays > 0 ? <span>только свежие: {ageDays} дн.</span> : null}
                <span>аккаунт: {accountName(search.account_id)}</span>
                {city ? <span>город: {regionName(city)}</span> : null}
                {includeCount > 0 ? <span>условий: {includeCount}</span> : null}
                {excludeCount > 0 ? (
                  <span className="text-amber-300/80">исключений: {excludeCount}</span>
                ) : null}
                {regionCount > 0 ? <span>городов: {regionCount}</span> : null}
                {excludeRegionCount > 0 ? (
                  <span className="text-sky-300/80">
                    не учитываем городов: {excludeRegionCount}
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
                  onClick={() => setTarget({ search })}
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
