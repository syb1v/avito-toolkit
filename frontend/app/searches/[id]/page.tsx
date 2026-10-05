import Link from "next/link";

import { AlertsPanel } from "@/app/components/alerts-panel";
import { CrawlPanel } from "@/app/components/crawl-panel";
import { DigestPanel } from "@/app/components/digest-panel";
import { InfoHint } from "@/app/components/info-hint";
import { EditSearchButton } from "@/app/components/edit-search-button";
import { ListingActions } from "@/app/components/listing-actions";
import { PriceChart } from "@/app/components/price-chart";
import { RegionFilter } from "@/app/components/region-filter";
import { StatCard } from "@/app/components/stat-card";
import {
  type ListingSort,
  fetchAccounts,
  fetchAlerts,
  fetchHistory,
  fetchListings,
  fetchSearchStats,
  fetchSearches,
  fetchSummary,
} from "@/lib/api";
import { formatDays, formatPercent, formatPrice, formatRelativeTime } from "@/lib/format";
import { regionName } from "@/lib/regions";

const LISTINGS_PAGE_SIZE = 100;

const SORT_OPTIONS: { value: ListingSort; label: string }[] = [
  { value: "position", label: "По позиции" },
  { value: "price_asc", label: "Сначала дешёвые" },
  { value: "price_desc", label: "Сначала дорогие" },
  { value: "new", label: "Новые" },
  { value: "status", label: "По статусу" },
];

const EXCLUDE_REASON_META: Record<string, { label: string; className: string }> = {
  manual: {
    label: "скрыто вручную",
    className: "border-amber-500/40 bg-amber-500/10 text-amber-200",
  },
  keyword: {
    label: "не по теме",
    className: "border-neutral-600 bg-neutral-800 text-neutral-300",
  },
  stopword: {
    label: "стоп-слово",
    className: "border-amber-500/40 bg-amber-500/10 text-amber-200",
  },
  region: {
    label: "другой город",
    className: "border-sky-500/40 bg-sky-500/10 text-sky-200",
  },
};

const CATEGORY_META: Record<string, { label: string; className: string }> = {
  copy: {
    label: "копия/реплика",
    className: "border-violet-500/40 bg-violet-500/10 text-violet-200",
  },
  fake_bait: {
    label: "приманка",
    className: "border-amber-500/40 bg-amber-500/10 text-amber-200",
  },
  irrelevant: {
    label: "нерелевант",
    className: "border-red-500/40 bg-red-500/10 text-red-200",
  },
  duplicate: {
    label: "дубль",
    className: "border-sky-500/40 bg-sky-500/10 text-sky-200",
  },
};

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    active: "border-emerald-500/30 bg-emerald-500/15 text-emerald-300",
    gone: "border-neutral-700 bg-neutral-800 text-neutral-400",
  };
  const labels: Record<string, string> = {
    active: "активно",
    gone: "снято",
  };
  return (
    <span
      className={`whitespace-nowrap rounded-full border px-2 py-0.5 text-xs ${
        styles[status] ?? "border-neutral-700 bg-neutral-800 text-neutral-400"
      }`}
    >
      {labels[status] ?? status}
    </span>
  );
}

function ListingFlags({
  flagged,
  category,
  reasons,
  description,
}: {
  flagged: boolean;
  category: string | null;
  reasons: string[] | null;
  description: string | null;
}) {
  if (!flagged && (!reasons || reasons.length === 0)) {
    return null;
  }
  const meta = category ? CATEGORY_META[category] : undefined;
  const tooltipParts: string[] = [...(reasons ?? [])];
  if (description) {
    tooltipParts.push(`Описание: ${description.slice(0, 300)}`);
  }
  return (
    <div className="mt-1 flex flex-col gap-1" title={tooltipParts.join("\n")}>
      <div className="flex flex-wrap gap-1">
        {flagged ? (
          <span
            className={`rounded border px-1.5 py-0.5 text-[10px] ${
              meta?.className ?? "border-amber-500/40 bg-amber-500/10 text-amber-200"
            }`}
          >
            {meta?.label ?? "подозрительное"}
          </span>
        ) : null}
        {(reasons ?? []).slice(0, 2).map((reason) => (
          <span
            key={reason}
            className="rounded border border-neutral-700 bg-neutral-800 px-1.5 py-0.5 text-[10px] text-neutral-400"
          >
            {reason}
          </span>
        ))}
      </div>
      {flagged && description ? (
        <span className="line-clamp-2 text-[11px] text-neutral-500">{description}</span>
      ) : null}
    </div>
  );
}

export default async function SearchDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{
    flagged?: string;
    category?: string;
    excluded?: string;
    region?: string;
    sort?: string;
    fresh?: string;
    page?: string;
  }>;
}) {
  const [{ id }, query] = await Promise.all([params, searchParams]);
  const flaggedOnly = query?.flagged === "1";
  const categoryFilter = query?.category ?? null;
  const excludedOnly = query?.excluded === "1";
  const regionFilter = query?.region ?? null;
  const freshOnly = query?.fresh === "1";
  const pageNumber = Math.max(1, Number(query?.page) || 1);
  const sortParam = query?.sort ?? "position";
  const sortOption: ListingSort = (
    SORT_OPTIONS.some((option) => option.value === sortParam) ? sortParam : "position"
  ) as ListingSort;

  const hrefWith = (changes: Record<string, string | null>): string => {
    const next = new URLSearchParams();
    const current: Record<string, string | null> = {
      flagged: flaggedOnly ? "1" : null,
      category: categoryFilter,
      excluded: excludedOnly ? "1" : null,
      region: regionFilter,
      sort: sortOption !== "position" ? sortOption : null,
      fresh: freshOnly ? "1" : null,
      page: pageNumber > 1 ? String(pageNumber) : null,
      ...changes,
    };
    if (!("page" in changes)) {
      current.page = null;
    }
    for (const [key, value] of Object.entries(current)) {
      if (value) {
        next.set(key, value);
      }
    }
    const suffix = next.toString();
    return `/searches/${id}${suffix ? `?${suffix}` : ""}`;
  };

  const [summary, history, alerts, listings, listingStats, allSearches, accounts] =
    await Promise.all([
    fetchSummary(id),
    fetchHistory(id),
    fetchAlerts(id),
    fetchListings(id, {
      flagged: flaggedOnly ? true : undefined,
      category: categoryFilter ?? undefined,
      excluded: excludedOnly ? true : undefined,
      region: regionFilter ?? undefined,
      sort: sortOption,
      fresh: freshOnly ? true : undefined,
      limit: LISTINGS_PAGE_SIZE,
      offset: (pageNumber - 1) * LISTINGS_PAGE_SIZE,
    }),
    fetchSearchStats(id),
    fetchSearches(),
    fetchAccounts(),
  ]);
  const currentSearch = allSearches.find((item) => item.id === id) ?? null;

  if (summary === null) {
    return (
      <main className="mx-auto max-w-3xl px-4 py-12 sm:px-6 sm:py-16">
        <Link href="/" className="text-sm text-neutral-500 hover:text-neutral-300">
          ← Все поиски
        </Link>
        <div className="mt-6 rounded-xl border border-amber-500/30 bg-amber-500/10 p-5 text-sm text-amber-200">
          Поиск не найден или API недоступен. Проверьте, что backend запущен и
          идентификатор поиска существует.
        </div>
      </main>
    );
  }

  const stats = summary.stats;
  const excludedCount = listingStats?.excluded ?? 0;
  const freshCount = listingStats?.fresh ?? 0;
  const regionCounts: Record<string, number> = Object.fromEntries(
    (listingStats?.regions ?? []).map((item) => [item.region, item.count]),
  );
  const totalListings = listingStats?.total ?? listings.length;
  const hasMore = listings.length === LISTINGS_PAGE_SIZE;

  return (
    <main className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-8 sm:gap-8 sm:px-6 sm:py-12">
      <header className="flex flex-col gap-2">
        <Link href="/" className="text-sm text-neutral-500 hover:text-neutral-300">
          ← Все поиски
        </Link>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-xl font-semibold tracking-tight sm:text-2xl">
            {summary.name}
          </h1>
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`rounded-full border px-3 py-1 text-xs ${
                summary.is_active
                  ? "border-emerald-500/30 bg-emerald-500/15 text-emerald-300"
                  : "border-neutral-700 bg-neutral-800 text-neutral-400"
              }`}
            >
              {summary.is_active ? "активен" : "на паузе"}
            </span>
            {currentSearch ? (
              <EditSearchButton search={currentSearch} accounts={accounts} />
            ) : null}
          </div>
        </div>
        <a
          href={summary.url}
          target="_blank"
          rel="noreferrer"
          className="truncate text-sm text-neutral-500 underline decoration-neutral-800 underline-offset-4 hover:text-neutral-300"
        >
          {summary.url}
        </a>
      </header>

      <CrawlPanel searchId={id} />

      <section className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-6">
        <StatCard
          label="Активных"
          value={String(summary.active_count)}
          info="Сколько объявлений сейчас в активной выдаче поиска по последнему обходу."
        />
        <StatCard
          label="Новых сегодня"
          value={String(summary.new_today_count)}
          info="Объявления, впервые появившиеся в этой выдаче за сегодня."
        />
        <StatCard
          label="Снято сегодня"
          value={String(summary.delisted_today_count)}
          info="Объявления из выдачи, которые исчезли сегодня (сняты или проданы)."
        />
        <StatCard
          label="Снято за 7 дней"
          value={String(summary.delisted_7d)}
          info="Сколько объявлений исчезло из выдачи за последние 7 дней."
        />
        <StatCard
          label="Вымывание"
          value={formatPercent(summary.delisting_velocity)}
          hint="снято/активные за 7д"
          info="Прокси-спрос: снято за 7 дней ÷ активные. Больше 35% — рынок горячий (держим цену у P75), меньше 17.5% — вялый (уходим к P25)."
        />
        <StatCard
          label="Срок жизни"
          value={formatDays(summary.avg_lifetime_days)}
          hint="средний по снятым"
          info="Среднее время от первого появления объявления в выдаче до его исчезновения."
        />
      </section>

      <AlertsPanel alerts={alerts.filter((alert) => alert.status === "new")} searchId={id} />

      <DigestPanel searchId={id} />

      <section className="rounded-xl border border-neutral-800 bg-neutral-900/60 p-4 sm:p-5">
        <div className="flex items-center">
          <h2 className="text-base font-medium sm:text-lg">Цены рынка</h2>
          <InfoHint
            title="Как считаем цены"
            text="Берём цены активных объявлений и отсекаем выбросы методом IQR: IQR = P75 − P25, всё вне [P25 − 1.5·IQR; P75 + 1.5·IQR] отбрасывается. Подозрительные карточки (копии/реплики, аномальные цены, дубли) исключаются из статистики — их видно по бейджам в выдаче."
          />
        </div>
        {stats !== null && summary.flagged_count > 0 ? (
          <p className="mt-2 text-xs text-amber-300/80">
            Исключено подозрительных из статистики: {summary.flagged_count}
          </p>
        ) : null}
        {stats !== null && summary.keyword_excluded > 0 ? (
          <p className="mt-1 text-xs text-neutral-500">
            Не по теме товара (include-фильтр): {summary.keyword_excluded}
          </p>
        ) : null}
        {stats !== null && summary.stopword_excluded > 0 ? (
          <p className="mt-1 text-xs text-amber-300/80">
            Исключено стоп-словами: {summary.stopword_excluded}
          </p>
        ) : null}
        {stats !== null && summary.region_excluded > 0 ? (
          <p className="mt-1 text-xs text-sky-300/80">
            Отсеяно по городам: {summary.region_excluded}
          </p>
        ) : null}
        {stats !== null && summary.manual_excluded > 0 ? (
          <p className="mt-1 text-xs text-amber-300/80">
            Скрыто вручную из расчёта: {summary.manual_excluded}
          </p>
        ) : null}
        {stats === null ? (
          <p className="mt-3 text-sm text-neutral-500">
            Нет активных объявлений с ценой — выполните обход поиска.
          </p>
        ) : (
          <div className="mt-4 grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-6">
            <StatCard
              label="Медиана"
              value={formatPrice(stats.median)}
              accent="info"
              hint="середина рынка"
              info="Середина рынка: ровно половина цен ниже, половина выше. Устойчива к выбросам."
            />
            <StatCard
              label="Средняя"
              value={formatPrice(stats.mean)}
              info="Арифметическое среднее по очищенной выборке. Сильнее реагирует на дорогие лоты, чем медиана."
            />
            <StatCard
              label="P25"
              value={formatPrice(stats.p25)}
              hint="25% лотов дешевле"
              info="25-й перцентиль: 25% объявлений дешевле этой цены. Нижняя граница «среднего» рынка."
            />
            <StatCard
              label="P75"
              value={formatPrice(stats.p75)}
              hint="25% лотов дороже"
              info="75-й перцентиль: 25% объявлений дороже этой цены. Верхняя граница «среднего» рынка."
            />
            <StatCard
              label="Минимум"
              value={formatPrice(stats.price_min)}
              info="Самая низкая цена после IQR-фильтрации выбросов."
            />
            <StatCard
              label="Максимум"
              value={formatPrice(stats.price_max)}
              hint={`выборка: ${stats.count}`}
              info="Самая высокая цена после IQR-фильтрации. В подписи — сколько цен осталось в выборке."
            />
          </div>
        )}
      </section>

      <section className="rounded-xl border border-neutral-800 bg-neutral-900/60">
        <h2 className="px-4 pt-4 text-base font-medium sm:px-5 sm:pt-5 sm:text-lg">
          Динамика цен
        </h2>
        <PriceChart data={history} />
      </section>

      <section className="rounded-xl border border-neutral-800">
        <div className="flex flex-wrap items-center justify-between gap-3 px-4 pt-4 sm:px-5">
          <div className="flex items-center">
            <h2 className="text-base font-medium sm:text-lg">
              {flaggedOnly || categoryFilter ? "Подозрительные" : "Выдача"}
            </h2>
            <InfoHint
              title="Как выявляем подозрительные"
              text="Категории: копия/реплика — слова «копия», «реплика», «1:1»; приманка — цена ниже 35% медианы или фразы-приманки; нерелевант — запчасти, неисправности, «под восстановление»; дубль — одинаковые название+цена у 5+ продавцов. Для кандидатов догружаются описания объявлений (до 10 за обход), затем DeepSeek оценивает карточки батчами (до 40) и возвращает категорию и причину. Исключающие фильтры поиска (стоп-слова) убирают лот из статистики цен, но он остаётся здесь с пометкой «фильтр»."
            />
          </div>
          <span className="text-xs text-neutral-500">
            показано {listings.length} из {totalListings}
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-2 px-4 pb-2 pt-1 sm:px-5">
          <Link
            href={hrefWith({ flagged: null, category: null, excluded: null, region: null })}
            className={`rounded-full border px-2.5 py-1 text-xs transition ${
              !flaggedOnly && !categoryFilter && !excludedOnly && !regionFilter
                ? "border-neutral-500 bg-neutral-800 text-neutral-100"
                : "border-neutral-800 text-neutral-400 hover:border-neutral-600"
            }`}
          >
            Все
          </Link>
          {summary.max_age_days > 0 ? (
            <Link
              href={hrefWith({
                fresh: freshOnly ? null : "1",
              })}
              className={`rounded-full border px-2.5 py-1 text-xs transition ${
                freshOnly
                  ? "border-emerald-500/60 bg-emerald-500/15 text-emerald-100"
                  : "border-neutral-800 text-neutral-400 hover:border-neutral-600"
              }`}
            >
              Свежие {summary.max_age_days} дн. ({freshCount})
            </Link>
          ) : null}
          {excludedCount > 0 ? (
            <Link
              href={hrefWith({
                excluded: "1",
                flagged: null,
                category: null,
                region: null,
              })}
              className={`rounded-full border px-2.5 py-1 text-xs transition ${
                excludedOnly
                  ? "border-amber-500/60 bg-amber-500/15 text-amber-100"
                  : "border-neutral-800 text-neutral-400 hover:border-neutral-600"
              }`}
            >
              Вне расчёта ({excludedCount})
            </Link>
          ) : null}
          {summary.flagged_count > 0 ? (
            <Link
              href={hrefWith({
                flagged: "1",
                category: null,
                excluded: null,
                region: null,
              })}
              className={`rounded-full border px-2.5 py-1 text-xs transition ${
                flaggedOnly
                  ? "border-amber-500/60 bg-amber-500/15 text-amber-100"
                  : "border-neutral-800 text-neutral-400 hover:border-neutral-600"
              }`}
            >
              Подозрительные ({summary.flagged_count})
            </Link>
          ) : null}
          {Object.entries(summary.flag_categories).map(([key, count]) => {
            const meta = CATEGORY_META[key];
            if (!meta) {
              return null;
            }
            const active = categoryFilter === key;
            return (
              <Link
                key={key}
                href={hrefWith({
                  category: key,
                  flagged: null,
                  excluded: null,
                  region: null,
                })}
                className={`rounded-full border px-2.5 py-1 text-xs transition ${meta.className} ${
                  active ? "ring-1 ring-neutral-400/60" : "opacity-80 hover:opacity-100"
                }`}
              >
                {meta.label} ({count})
              </Link>
            );
          })}
        </div>

        <div className="flex flex-wrap items-center gap-2 px-4 pb-3 sm:px-5">
          <RegionFilter current={regionFilter} counts={regionCounts} />
        </div>

        <div className="flex flex-wrap items-center gap-2 px-4 pb-3 sm:px-5">
          <span className="text-[11px] uppercase tracking-wider text-neutral-600">
            сортировка:
          </span>
          {SORT_OPTIONS.map((option) => (
            <Link
              key={option.value}
              href={hrefWith({
                sort: option.value === "position" ? null : option.value,
              })}
              className={`rounded-full border px-2.5 py-1 text-xs transition ${
                sortOption === option.value
                  ? "border-emerald-500/50 bg-emerald-500/10 text-emerald-200"
                  : "border-neutral-800 text-neutral-400 hover:border-neutral-600"
              }`}
            >
              {option.label}
            </Link>
          ))}
        </div>

        <div className="hidden overflow-x-auto md:block">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-y border-neutral-800 text-left text-xs uppercase tracking-wider text-neutral-500">
                <th className="px-5 py-3 font-medium">#</th>
                <th className="px-5 py-3 font-medium">Объявление</th>
                <th className="px-5 py-3 text-right font-medium">Цена</th>
                <th className="px-5 py-3 font-medium">Статус</th>
                <th className="px-5 py-3 text-right font-medium">Расчёт</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-800">
              {listings.map((listing) => (
                <tr key={listing.id} className="hover:bg-neutral-900/60">
                  <td className="px-5 py-3 tabular-nums text-neutral-500">
                    {listing.last_position ?? "—"}
                  </td>
                  <td className="max-w-xl px-5 py-3">
                    {listing.url ? (
                      <a
                        href={listing.url}
                        target="_blank"
                        rel="noreferrer"
                        className="line-clamp-1 hover:underline"
                        title={listing.title}
                      >
                        {listing.title}
                      </a>
                    ) : (
                      <span className="line-clamp-1" title={listing.title}>
                        {listing.title}
                      </span>
                    )}
                    <span className="text-xs text-neutral-500">
                      id {listing.id}
                      {listing.region ? ` · ${regionName(listing.region)}` : ""}
                      {listing.first_seen
                        ? ` · в базе ${formatRelativeTime(listing.first_seen)}`
                        : ""}
                    </span>
                    {listing.exclude_reason ? (
                      <span
                        className={`ml-2 rounded border px-1.5 py-0.5 text-[10px] ${
                          EXCLUDE_REASON_META[listing.exclude_reason]?.className ?? ""
                        }`}
                        title={listing.exclude_detail ?? undefined}
                      >
                        {EXCLUDE_REASON_META[listing.exclude_reason]?.label ??
                          listing.exclude_reason}
                        {listing.exclude_detail ? ` · ${listing.exclude_detail}` : ""}
                      </span>
                    ) : null}
                    <ListingFlags
                      flagged={listing.is_flagged}
                      category={listing.flag_category}
                      reasons={listing.flag_reasons}
                      description={listing.description_snippet}
                    />
                  </td>
                  <td className="px-5 py-3 text-right tabular-nums">
                    {formatPrice(listing.price)}
                  </td>
                  <td className="px-5 py-3">
                    <StatusBadge status={listing.status} />
                  </td>
                  <td className="px-5 py-3 text-right">
                    <ListingActions
                      searchId={id}
                      listingId={listing.id}
                      manualExcluded={listing.manual_excluded}
                    />
                  </td>
                </tr>
              ))}
              {listings.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-5 py-10 text-center text-neutral-500">
                    Пока пусто — выполните обход поиска.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <ul className="flex flex-col divide-y divide-neutral-800 md:hidden">
          {listings.map((listing) => (
            <li key={listing.id} className="flex items-start justify-between gap-3 px-4 py-3">
              <div className="min-w-0">
                <p className="text-xs tabular-nums text-neutral-500">
                  #{listing.last_position ?? "—"} · id {listing.id}
                  {listing.region ? ` · ${regionName(listing.region)}` : ""}
                  {listing.first_seen
                    ? ` · в базе ${formatRelativeTime(listing.first_seen)}`
                    : ""}
                  {listing.exclude_reason
                    ? ` · ${EXCLUDE_REASON_META[listing.exclude_reason]?.label ?? listing.exclude_reason}${
                        listing.exclude_detail ? ` (${listing.exclude_detail})` : ""
                      }`
                    : ""}
                </p>
                {listing.url ? (
                  <a
                    href={listing.url}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-0.5 line-clamp-2 text-sm hover:underline"
                  >
                    {listing.title}
                  </a>
                ) : (
                  <p className="mt-0.5 line-clamp-2 text-sm">{listing.title}</p>
                )}
                <div className="mt-1.5 flex items-center gap-2">
                  <StatusBadge status={listing.status} />
                  <ListingActions
                    searchId={id}
                    listingId={listing.id}
                    manualExcluded={listing.manual_excluded}
                  />
                </div>
                <ListingFlags
                  flagged={listing.is_flagged}
                  category={listing.flag_category}
                  reasons={listing.flag_reasons}
                  description={listing.description_snippet}
                />
              </div>
              <p className="whitespace-nowrap text-sm font-medium tabular-nums">
                {formatPrice(listing.price)}
              </p>
            </li>
          ))}
          {listings.length === 0 && (
            <li className="px-4 py-10 text-center text-sm text-neutral-500">
              Пока пусто — выполните обход поиска.
            </li>
          )}
        </ul>

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-neutral-800 px-4 py-3 sm:px-5">
          <span className="text-xs text-neutral-500">
            страница {pageNumber}
            {hasMore
              ? " · есть ещё"
              : pageNumber > 1
                ? " · это конец списка"
                : ""}
          </span>
          <div className="flex gap-2">
            {pageNumber > 1 ? (
              <Link
                href={hrefWith({
                  page: pageNumber - 1 === 1 ? null : String(pageNumber - 1),
                })}
                className="rounded-lg border border-neutral-700 px-3 py-1 text-xs text-neutral-300 transition hover:border-neutral-500"
              >
                ← Назад
              </Link>
            ) : null}
            {hasMore ? (
              <Link
                href={hrefWith({ page: String(pageNumber + 1) })}
                className="rounded-lg border border-sky-500/40 bg-sky-500/10 px-3 py-1 text-xs text-sky-200 transition hover:bg-sky-500/20"
              >
                Показать ещё {LISTINGS_PAGE_SIZE} →
              </Link>
            ) : null}
          </div>
        </div>
      </section>
    </main>
  );
}
