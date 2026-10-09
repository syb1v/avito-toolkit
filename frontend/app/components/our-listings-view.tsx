"use client";

import { useEffect, useMemo, useState } from "react";

import { InfoHint } from "@/app/components/info-hint";
import { SkuEdits } from "@/app/components/sku-edits";
import { SkuModal } from "@/app/components/sku-modal";
import {
  fetchEditsClient,
  type ListingEdit,
  type OurListingOverview,
  type Recommendation,
} from "@/lib/api";
import { formatPercent, formatPrice } from "@/lib/format";

const STRATEGY_LABELS: Record<string, string> = {
  undercut_p25: "Демпинг P25−1%",
  match_median: "По медиане",
  premium_p75: "Премиум P75",
  keep_current: "Держать цену",
  manual: "Своя цена",
};

const EDIT_STATUS_LABELS: Record<string, string> = {
  draft: "черновик",
  approved: "одобрено",
  applied: "применено",
  reverted: "откачено",
  rejected: "отклонено",
  failed: "ошибка",
};

function DeltaText({ deltaPct }: { deltaPct: number | null }) {
  if (deltaPct === null) {
    return <span className="text-neutral-500">—</span>;
  }
  const positive = deltaPct > 0;
  return (
    <span className={positive ? "text-amber-300" : "text-emerald-300"}>
      {positive ? "+" : ""}
      {formatPercent(deltaPct / 100)}
    </span>
  );
}

export function OurListingsView({
  rows,
  recommendations,
  initialSku,
}: {
  rows: OurListingOverview[];
  recommendations: Recommendation[];
  initialSku?: string | null;
}) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [accountFilter, setAccountFilter] = useState("");
  const [onlyRecommended, setOnlyRecommended] = useState(false);
  const [onlyWithEdits, setOnlyWithEdits] = useState(false);
  const [edits, setEdits] = useState<ListingEdit[]>([]);
  const [selectedSku, setSelectedSku] = useState<string | null>(initialSku ?? null);

  useEffect(() => {
    fetchEditsClient(undefined, 200).then((data) => {
      if (data) {
        setEdits(data.items);
      }
    });
  }, []);

  const recommendedSkus = useMemo(
    () => new Set(recommendations.map((item) => item.sku)),
    [recommendations],
  );
  const lastEditBySku = useMemo(() => {
    const map = new Map<string, ListingEdit>();
    for (const edit of edits) {
      if (!map.has(edit.sku)) {
        map.set(edit.sku, edit);
      }
    }
    return map;
  }, [edits]);

  const statusOptions = useMemo(() => {
    const values = new Set<string>();
    for (const row of rows) {
      if (row.avito_status) {
        values.add(row.avito_status);
      }
    }
    return [...values].sort();
  }, [rows]);

  const accountOptions = useMemo(() => {
    const values = new Set<string>();
    for (const row of rows) {
      if (row.account) {
        values.add(row.account);
      }
    }
    return [...values].sort();
  }, [rows]);

  const filteredRows = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return rows.filter((row) => {
      if (needle && !`${row.title} ${row.sku}`.toLowerCase().includes(needle)) {
        return false;
      }
      if (status && row.avito_status !== status) {
        return false;
      }
      if (accountFilter) {
        const account = row.account ?? "Без продавца";
        if (account !== accountFilter) {
          return false;
        }
      }
      if (onlyRecommended && !recommendedSkus.has(row.sku)) {
        return false;
      }
      if (onlyWithEdits && !lastEditBySku.has(row.sku)) {
        return false;
      }
      return true;
    });
  }, [
    rows,
    query,
    status,
    accountFilter,
    onlyRecommended,
    onlyWithEdits,
    recommendedSkus,
    lastEditBySku,
  ]);

  const rowBySku = useMemo(() => {
    const map = new Map<string, OurListingOverview>();
    for (const row of rows) {
      map.set(row.sku, row);
    }
    return map;
  }, [rows]);
  const recBySku = useMemo(() => {
    const map = new Map<string, Recommendation>();
    for (const item of recommendations) {
      map.set(item.sku, item);
    }
    return map;
  }, [recommendations]);

  const groups = useMemo(() => {
    const map = new Map<string, { rows: OurListingOverview[]; recs: Recommendation[] }>();
    for (const row of filteredRows) {
      const key = row.account ?? "Без продавца";
      const group = map.get(key) ?? { rows: [], recs: [] };
      group.rows.push(row);
      const rec = recBySku.get(row.sku);
      if (rec) {
        group.recs.push(rec);
      }
      map.set(key, group);
    }
    return [...map.entries()];
  }, [filteredRows, recBySku]);

  function renderRecommendations(items: Recommendation[]) {
    if (items.length === 0) {
      return (
        <p className="rounded-xl border border-dashed border-neutral-800 p-4 text-xs text-neutral-500">
          Рекомендаций нет — нужны матчи с рынком (обход поисков + матчинг).
        </p>
      );
    }
    return (
      <ul className="grid gap-3 sm:grid-cols-2 sm:gap-4 lg:grid-cols-3">
        {items.map((item) => (
          <li
            key={item.sku}
            className="flex flex-col gap-3 rounded-xl border border-neutral-800 bg-neutral-900/60 p-4 transition hover:border-neutral-600"
          >
            <button
              type="button"
              onClick={() => setSelectedSku(item.sku)}
              className="flex flex-col gap-3 text-left"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate font-medium" title={item.title}>
                    {item.title}
                  </p>
                  <p className="font-mono text-xs text-neutral-500">{item.sku}</p>
                </div>
                <span className="whitespace-nowrap rounded-full border border-sky-500/30 bg-sky-500/10 px-2 py-0.5 text-xs text-sky-200">
                  {STRATEGY_LABELS[item.strategy] ?? item.strategy}
                </span>
              </div>
              <div className="flex items-end justify-between gap-3">
                <div>
                  <p className="text-xs text-neutral-500">Наша → цель</p>
                  <p className="text-sm tabular-nums">
                    {formatPrice(item.our_price)} →{" "}
                    <span className="font-medium">{formatPrice(item.clamped_price)}</span>
                  </p>
                </div>
                <DeltaText deltaPct={item.delta_pct} />
              </div>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-neutral-500">
                <span>медиана: {formatPrice(item.market_median)}</span>
                <span>матчей: {item.matched_count}</span>
                {item.requires_approval ? (
                  <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-amber-200">
                    нужно подтверждение
                  </span>
                ) : null}
              </div>
            </button>
            <SkuEdits sku={item.sku} />
            <button
              type="button"
              onClick={() => setSelectedSku(item.sku)}
              className="self-start text-xs text-sky-300/80 hover:underline"
            >
              Подробнее: рынок, конкуренты, AI-обоснование →
            </button>
          </li>
        ))}
      </ul>
    );
  }

  function renderTable(items: OurListingOverview[]) {
    return (
      <div className="rounded-xl border border-neutral-800">
        <div className="hidden overflow-x-auto md:block">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-neutral-800 text-left text-xs uppercase tracking-wider text-neutral-500">
                <th className="px-5 py-3 font-medium">SKU</th>
                <th className="px-5 py-3 font-medium">Объявление</th>
                <th className="px-5 py-3 text-right font-medium">Наша цена</th>
                <th className="px-5 py-3 text-right font-medium">Медиана рынка</th>
                <th className="px-5 py-3 text-right font-medium">Дельта</th>
                <th className="px-5 py-3 text-right font-medium">Матчей</th>
                <th className="px-5 py-3 font-medium">Авито</th>
                <th className="px-5 py-3 font-medium">Правка</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-800">
              {items.map((row) => {
                const lastEdit = lastEditBySku.get(row.sku);
                return (
                  <tr
                    key={row.sku}
                    className="cursor-pointer hover:bg-neutral-900/60"
                    onClick={() => setSelectedSku(row.sku)}
                  >
                    <td className="px-5 py-3 font-mono text-xs text-neutral-400">{row.sku}</td>
                    <td className="max-w-md px-5 py-3">
                      <span className="line-clamp-1" title={row.title}>
                        {row.title}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-right tabular-nums">
                      {formatPrice(row.our_price)}
                    </td>
                    <td className="px-5 py-3 text-right tabular-nums text-neutral-400">
                      {formatPrice(row.market_median)}
                    </td>
                    <td className="px-5 py-3 text-right tabular-nums">
                      <DeltaText deltaPct={row.delta_to_median_pct} />
                    </td>
                    <td className="px-5 py-3 text-right tabular-nums text-neutral-400">
                      {row.matched_count}
                    </td>
                    <td className="px-5 py-3">
                      {row.avito_url ? (
                        <a
                          href={row.avito_url}
                          target="_blank"
                          rel="noreferrer"
                          onClick={(event) => event.stopPropagation()}
                          className="text-xs text-sky-300/80 hover:underline"
                        >
                          объявление
                        </a>
                      ) : (
                        <span className="text-xs text-neutral-600">—</span>
                      )}
                    </td>
                    <td className="px-5 py-3">
                      {lastEdit ? (
                        <span className="whitespace-nowrap text-xs text-neutral-400">
                          {EDIT_STATUS_LABELS[lastEdit.status] ?? lastEdit.status} ·{" "}
                          {formatPrice(lastEdit.target_price)}
                        </span>
                      ) : (
                        <span className="text-xs text-neutral-600">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <ul className="flex flex-col divide-y divide-neutral-800 md:hidden">
          {items.map((row) => {
            const lastEdit = lastEditBySku.get(row.sku);
            return (
              <li
                key={row.sku}
                className="flex cursor-pointer flex-col gap-2 px-4 py-3"
                onClick={() => setSelectedSku(row.sku)}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm" title={row.title}>
                      {row.title}
                    </p>
                    <p className="font-mono text-xs text-neutral-500">{row.sku}</p>
                  </div>
                  {row.avito_status ? (
                    <span className="whitespace-nowrap rounded-full border border-emerald-500/30 bg-emerald-500/15 px-2 py-0.5 text-xs text-emerald-300">
                      {row.avito_status}
                    </span>
                  ) : null}
                </div>
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-neutral-400">
                  <span>
                    наша: <span className="tabular-nums">{formatPrice(row.our_price)}</span>
                  </span>
                  <span>
                    медиана:{" "}
                    <span className="tabular-nums">{formatPrice(row.market_median)}</span>
                  </span>
                  <span>
                    дельта: <DeltaText deltaPct={row.delta_to_median_pct} />
                  </span>
                  <span>матчей: {row.matched_count}</span>
                  {lastEdit ? (
                    <span>
                      правка: {EDIT_STATUS_LABELS[lastEdit.status] ?? lastEdit.status}
                    </span>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ul>
      </div>
    );
  }

  return (
    <>
      <section className="flex flex-wrap items-center gap-2 rounded-xl border border-neutral-800 bg-neutral-900/60 p-3">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Фильтр: название или SKU"
          className="min-w-[200px] flex-1 rounded-lg border border-neutral-800 bg-neutral-950 px-3 py-1.5 text-sm text-neutral-200 outline-none focus:border-sky-500/60"
        />
        <select
          value={accountFilter}
          onChange={(event) => setAccountFilter(event.target.value)}
          className="rounded-lg border border-neutral-800 bg-neutral-950 px-2 py-1.5 text-xs text-neutral-200 outline-none focus:border-sky-500/60"
        >
          <option value="">все продавцы</option>
          {accountOptions.map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value)}
          className="rounded-lg border border-neutral-800 bg-neutral-950 px-2 py-1.5 text-xs text-neutral-200 outline-none focus:border-sky-500/60"
        >
          <option value="">любой статус</option>
          {statusOptions.map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
        <label className="flex items-center gap-1.5 text-xs text-neutral-400">
          <input
            type="checkbox"
            checked={onlyRecommended}
            onChange={(event) => setOnlyRecommended(event.target.checked)}
          />
          с рекомендацией
        </label>
        <label className="flex items-center gap-1.5 text-xs text-neutral-400">
          <input
            type="checkbox"
            checked={onlyWithEdits}
            onChange={(event) => setOnlyWithEdits(event.target.checked)}
          />
          с правками
        </label>
        <span className="text-xs text-neutral-500">
          показано {filteredRows.length} из {rows.length}
        </span>
      </section>

      {groups.length === 0 ? (
        <p className="rounded-xl border border-dashed border-neutral-800 p-5 text-sm text-neutral-500">
          Ничего не найдено — ослабьте фильтры.
        </p>
      ) : (
        groups.map(([accountName, group]) => (
          <section key={accountName} className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-neutral-800 pb-2">
              <div className="flex items-center">
                <h2 className="text-lg font-medium">Продавец: {accountName}</h2>
                <InfoHint
                  title="Как выбирается стратегия"
                  text="По вымыванию спроса: горячий рынок (>35%) — премиум P75; вялый (<17.5%) — демпинг P25−1%; иначе медиана. Шаг за раз ≤5%, при изменении больше 10% — подтверждение. Клик по карточке или строке — детали, конкуренты и AI-обоснование."
                />
              </div>
              <span className="text-xs text-neutral-500">
                {group.rows.length} SKU · рекомендаций {group.recs.length}
              </span>
            </div>
            {renderRecommendations(group.recs)}
            {renderTable(group.rows)}
          </section>
        ))
      )}

      {selectedSku ? (
        <SkuModal
          sku={selectedSku}
          row={rowBySku.get(selectedSku)}
          recommendation={recBySku.get(selectedSku)}
          onClose={() => setSelectedSku(null)}
        />
      ) : null}
    </>
  );
}
