"use client";

import { useCallback, useEffect, useState } from "react";

import { fetchSearchSellers, updateSearchSellerClient, type SearchSellers } from "@/lib/api";
import { useToast } from "@/app/components/toast";

export function CompetitorRulesEditor({ searchId }: { searchId: string }) {
  const [data, setData] = useState<SearchSellers | null>(null);
  const [ref, setRef] = useState("");
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const load = useCallback(async () => setData(await fetchSearchSellers(searchId)), [searchId]);
  useEffect(() => { void load(); }, [load]);

  async function apply(value: string, mode: "target" | "exclude" | "remove_target" | "remove_exclude") {
    if (!value.trim()) return;
    setBusy(true);
    const result = await updateSearchSellerClient(searchId, value.trim(), mode);
    setBusy(false);
    if (!result.ok) { toast.push("error", result.error); return; }
    setData(result.data); setRef("");
    toast.push("success", mode.startsWith("remove") ? "Правило удалено" : mode === "target" ? "Продавец добавлен в whitelist" : "Продавец добавлен в blacklist");
  }

  const whitelist = data?.target_refs ?? [];
  const blacklist = data?.exclude_refs ?? [];
  return <section className="rounded-xl border border-neutral-800 bg-neutral-900/60 p-4 sm:p-5">
    <div><h2 className="text-base font-medium sm:text-lg">Фильтры конкурентов</h2><p className="mt-1 max-w-2xl text-xs text-neutral-500">Настройки действуют только для этого поиска. Если продавец попал в оба списка, blacklist имеет приоритет.</p></div>
    <div className="mt-4 grid gap-3 md:grid-cols-2">
      <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3"><p className="text-xs font-medium text-emerald-200">Whitelist · учитывать только</p><div className="mt-2 flex flex-wrap gap-1.5">{whitelist.length ? whitelist.map((item) => <span key={item} className="rounded-full border border-emerald-500/30 px-2 py-1 text-xs text-emerald-200">{item}<button type="button" aria-label={`Удалить ${item} из whitelist`} onClick={() => apply(item, "remove_target")} className="ml-1.5">×</button></span>) : <span className="text-xs text-neutral-500">Пусто: учитываются все продавцы.</span>}</div></div>
      <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-3"><p className="text-xs font-medium text-red-200">Blacklist · исключить всегда</p><div className="mt-2 flex flex-wrap gap-1.5">{blacklist.length ? blacklist.map((item) => <span key={item} className="rounded-full border border-red-500/30 px-2 py-1 text-xs text-red-200">{item}<button type="button" aria-label={`Удалить ${item} из blacklist`} onClick={() => apply(item, "remove_exclude")} className="ml-1.5">×</button></span>) : <span className="text-xs text-neutral-500">Пусто.</span>}</div></div>
    </div>
    <div className="mt-4 flex flex-wrap gap-2"><input value={ref} onChange={(event) => setRef(event.target.value)} placeholder="Ссылка или имя продавца…" aria-label="Ссылка или имя конкурента" className="min-w-64 flex-1 rounded-lg border border-neutral-800 bg-neutral-950 px-3 py-2 text-sm text-neutral-200 outline-none focus:border-sky-500/60" /><button type="button" disabled={busy || !ref.trim()} onClick={() => apply(ref, "target")} className="rounded-lg border border-emerald-500/40 px-3 py-2 text-xs text-emerald-200 hover:bg-emerald-500/10 disabled:opacity-50">Добавить в whitelist</button><button type="button" disabled={busy || !ref.trim()} onClick={() => apply(ref, "exclude")} className="rounded-lg border border-red-500/40 px-3 py-2 text-xs text-red-200 hover:bg-red-500/10 disabled:opacity-50">Добавить в blacklist</button></div>
    <p className="mt-3 text-[11px] text-neutral-600">Для массового изменения откройте раздел «Поиски», выберите карточки и примените правило через панель массовых действий.</p>
  </section>;
}
