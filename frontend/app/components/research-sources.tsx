"use client";

import { useState } from "react";

import { researchProductClient, type ResearchResult } from "@/lib/api";
import { formatRelativeTime } from "@/lib/format";

export function ResearchSources({ query }: { query: string }) {
  const [result, setResult] = useState<ResearchResult | null>(null);
  const [busy, setBusy] = useState(false);

  async function research() {
    setBusy(true);
    const response = await researchProductClient(query);
    setBusy(false);
    if (response.ok) setResult(response.data);
  }

  return (
    <div className="mt-3 rounded-lg border border-neutral-800 bg-neutral-950/40 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2"><div><p className="text-xs font-medium text-neutral-300">Проверка модели в интернете</p><p className="mt-1 text-[11px] text-neutral-600">Источники помогают проверить идентичность, но не заменяют цены Авито.</p></div><button type="button" onClick={research} disabled={busy} className="rounded-lg border border-violet-500/40 bg-violet-500/10 px-3 py-1 text-xs text-violet-200 transition hover:bg-violet-500/20 disabled:opacity-50">{busy ? "Ищу источники…" : "Проверить модель"}</button></div>
      {result ? <div className="mt-3">{result.sources.length === 0 ? <p className="text-xs text-amber-200">Надёжный источник не найден. Рекомендация требует ручной проверки.</p> : <ul className="flex flex-col gap-2">{result.sources.map((source) => <li key={source.url} className="text-xs"><a href={source.url} target="_blank" rel="noreferrer" className="text-sky-300 underline-offset-4 hover:underline">{source.title}</a><span className="ml-2 text-neutral-600">{formatRelativeTime(source.retrieved_at)}</span><p className="mt-1 text-neutral-500">{source.claims.join(" · ")}</p></li>)}</ul>}</div> : null}
    </div>
  );
}
