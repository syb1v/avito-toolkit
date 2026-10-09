"use client";

import { useEffect, useState } from "react";

import { Modal } from "@/app/components/modal";
import { SkuEdits } from "@/app/components/sku-edits";
import { useToast } from "@/app/components/toast";
import {
  createAdviceClient,
  fetchMatchesClient,
  type OurListingOverview,
  type OurMatch,
  type PriceAdvice,
  type Recommendation,
} from "@/lib/api";
import { formatPercent, formatPrice } from "@/lib/format";
import { STRATEGY_LABELS } from "@/lib/terms";

export function SkuModal({
  sku,
  row,
  recommendation,
  onClose,
}: {
  sku: string;
  row: OurListingOverview | undefined;
  recommendation: Recommendation | undefined;
  onClose: () => void;
}) {
  const [matches, setMatches] = useState<OurMatch[] | null>(null);
  const [advice, setAdvice] = useState<PriceAdvice | null>(null);
  const [adviceBusy, setAdviceBusy] = useState(false);
  const toast = useToast();

  useEffect(() => {
    let cancelled = false;
    fetchMatchesClient(sku).then((data) => {
      if (!cancelled) {
        setMatches(data);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [sku]);

  async function explain() {
    setAdviceBusy(true);
    const result = await createAdviceClient(sku);
    setAdviceBusy(false);
    if (result.error) {
      toast.push("error", result.error);
      return;
    }
    setAdvice(result.advice ?? null);
  }

  const target = recommendation?.clamped_price ?? null;

  return (
    <Modal
      open
      onClose={onClose}
      title={row?.title ?? recommendation?.title ?? sku}
      subtitle={`SKU ${sku}${row?.avito_status ? ` · ${row.avito_status}` : ""}`}
      maxWidth="max-w-3xl"
      footer={
        <button
          type="button"
          onClick={onClose}
          className="rounded-lg border border-neutral-700 px-4 py-1.5 text-xs text-neutral-300 transition hover:border-neutral-500"
        >
          Закрыть
        </button>
      }
    >
      <div className="flex flex-col gap-4">
        <section className="rounded-lg border border-neutral-800 bg-neutral-950/40 p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs uppercase tracking-wider text-neutral-500">
              Рекомендация
            </p>
            {recommendation ? (
              <span className="rounded-full border border-sky-500/30 bg-sky-500/10 px-2 py-0.5 text-xs text-sky-200">
                {STRATEGY_LABELS[recommendation.strategy] ?? recommendation.strategy}
              </span>
            ) : (
              <span className="text-xs text-neutral-500">нет рекомендации (мало матчей)</span>
            )}
          </div>
          <div className="mt-2 grid gap-2 text-sm sm:grid-cols-2">
            <p>
              Наша цена: <b>{formatPrice(row?.our_price ?? recommendation?.our_price ?? null)}</b>
              {target !== null ? (
                <>
                  {" "}
                  → цель: <b className="text-emerald-300">{formatPrice(target)}</b>{" "}
                  {recommendation ? (
                    <span className="text-xs text-neutral-400">
                      ({recommendation.delta_pct > 0 ? "+" : ""}
                      {formatPercent(recommendation.delta_pct / 100)})
                    </span>
                  ) : null}
                </>
              ) : null}
            </p>
            <p className="text-neutral-400">
              Рынок: медиана {formatPrice(row?.market_median ?? null)} · P25{" "}
              {formatPrice(row?.market_p25 ?? null)} · P75 {formatPrice(row?.market_p75 ?? null)}
            </p>
            <p className="text-neutral-400">
              Матчей: {row?.matched_count ?? recommendation?.matched_count ?? 0}
              {row?.cheaper_share !== null && row?.cheaper_share !== undefined
                ? ` · дешевле нас: ${formatPercent(row.cheaper_share)}`
                : ""}
            </p>
            <p className="text-neutral-400">
              Себестоимость: {row?.cost_price != null ? formatPrice(row.cost_price) : "не задана"}
            </p>
          </div>
          <p className="mt-2 text-xs text-neutral-500">
            Что поменять: цена меняется только в пределах шага (±5%) и не ниже себестоимости;
            всё, что больше 10%, требует подтверждения. Ниже — ручная цена и журнал правок.
          </p>
        </section>

        <section>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs uppercase tracking-wider text-neutral-500">
              AI-обоснование
            </p>
            <button
              type="button"
              disabled={adviceBusy}
              onClick={explain}
              className="rounded-lg border border-violet-500/40 bg-violet-500/10 px-2.5 py-1 text-xs text-violet-200 transition hover:bg-violet-500/20 disabled:opacity-50"
            >
              {adviceBusy ? "AI думает…" : advice ? "Объяснить ещё раз" : "Объяснить через AI"}
            </button>
          </div>
          {advice ? (
            <div className="mt-2 rounded-lg border border-violet-500/20 bg-violet-500/5 p-3 text-sm text-neutral-300">
              <p>
                AI предлагает {formatPrice(advice.recommended_price)} · уверенность{" "}
                {formatPercent(advice.confidence_score)}
              </p>
              <ul className="mt-1 list-disc space-y-1 pl-5 text-xs text-neutral-400">
                {advice.justification_points.map((point) => (
                  <li key={point}>{point}</li>
                ))}
              </ul>
              <p className="mt-1 text-xs text-amber-300/80">Риски: {advice.risk_assessment}</p>
            </div>
          ) : (
            <p className="mt-2 text-xs text-neutral-500">
              Точечный вызов LLM (~$0.0005): объяснит, почему цена такая и что поменять.
            </p>
          )}
        </section>

        <section>
          <p className="mb-2 text-xs uppercase tracking-wider text-neutral-500">
            Правки и своя цена
          </p>
          <SkuEdits sku={sku} />
        </section>

        <section>
          <p className="mb-2 text-xs uppercase tracking-wider text-neutral-500">
            Сматченные конкуренты ({matches?.length ?? 0})
          </p>
          {matches === null ? (
            <p className="text-xs text-neutral-600">Загружаются…</p>
          ) : matches.length === 0 ? (
            <p className="text-xs text-neutral-600">
              Матчей нет — обход поисков ещё не собрал конкурентов.
            </p>
          ) : (
            <ul className="flex max-h-56 flex-col gap-1 overflow-y-auto text-xs">
              {matches.map((match) => (
                <li
                  key={match.listing_id}
                  className="flex items-center justify-between gap-2 rounded border border-neutral-800 bg-neutral-950/40 px-2.5 py-1.5"
                >
                  <span className="min-w-0 truncate text-neutral-300">
                    {match.url ? (
                      <a href={match.url} target="_blank" rel="noreferrer" className="hover:underline">
                        {match.title}
                      </a>
                    ) : (
                      match.title
                    )}
                  </span>
                  <span className="whitespace-nowrap tabular-nums text-neutral-400">
                    {formatPrice(match.price)} ·{" "}
                    {(match.similarity_score * 100).toFixed(0)}%
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </Modal>
  );
}
