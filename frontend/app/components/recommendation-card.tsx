"use client";

import { useState } from "react";

import { SkuEdits } from "@/app/components/sku-edits";
import { ResearchSources } from "@/app/components/research-sources";
import { type Recommendation } from "@/lib/api";
import { formatPercent, formatPrice } from "@/lib/format";

export function RecommendationCard({ item }: { item: Recommendation }) {
  const [open, setOpen] = useState(false);
  return (
    <article className="rounded-xl border border-neutral-800 bg-neutral-900/60 p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="font-medium text-neutral-100">{item.title}</h2>
          <p className="mt-1 text-xs text-neutral-500">SKU: {item.sku} · стратегия: {item.strategy}</p>
        </div>
        <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2.5 py-1 text-xs text-amber-200">требует проверки</span>
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-4">
        <div><p className="text-[11px] uppercase tracking-wide text-neutral-600">Сейчас</p><p className="mt-1 tabular-nums text-lg text-neutral-200">{formatPrice(item.our_price)}</p></div>
        <div><p className="text-[11px] uppercase tracking-wide text-neutral-600">Предложение</p><p className="mt-1 tabular-nums text-lg text-sky-200">{formatPrice(item.clamped_price)}</p></div>
        <div><p className="text-[11px] uppercase tracking-wide text-neutral-600">Медиана</p><p className="mt-1 tabular-nums text-lg text-neutral-300">{item.market_median === null ? "—" : formatPrice(item.market_median)}</p></div>
        <div><p className="text-[11px] uppercase tracking-wide text-neutral-600">Сравнений</p><p className="mt-1 tabular-nums text-lg text-neutral-300">{item.matched_count}</p></div>
      </div>
      <p className="mt-3 text-sm text-neutral-400">Изменение: {formatPercent(item.delta_pct / 100)} · {item.requires_approval ? "нужно подтверждение" : "в пределах правила"}</p>
      <ResearchSources query={item.title} />
      <button type="button" onClick={() => setOpen((value) => !value)} className="mt-4 rounded-lg border border-neutral-700 px-3 py-1.5 text-xs text-neutral-300 transition hover:border-neutral-500">{open ? "Скрыть точечное редактирование" : "Редактировать эту позицию"}</button>
      {open ? <div className="mt-3"><SkuEdits sku={item.sku} /></div> : null}
    </article>
  );
}
