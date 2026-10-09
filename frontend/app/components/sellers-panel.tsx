"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { fetchSearchSellers, updateSearchSellerClient, type SearchSellers } from "@/lib/api";
import { InfoHint } from "@/app/components/info-hint";
import { useToast } from "@/app/components/toast";

export function SellersPanel({ searchId }: { searchId: string }) {
  const [data, setData] = useState<SearchSellers | null>(null);
  const [ref, setRef] = useState("");
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const toast = useToast();
  const router = useRouter();

  const load = useCallback(async () => {
    const result = await fetchSearchSellers(searchId);
    if (result) {
      setData(result);
    }
  }, [searchId]);

  useEffect(() => {
    load();
  }, [load]);

  async function apply(
    value: string,
    mode: "target" | "exclude" | "remove_target" | "remove_exclude",
  ) {
    if (!value.trim()) {
      return;
    }
    setBusy(true);
    const result = await updateSearchSellerClient(searchId, value.trim(), mode);
    setBusy(false);
    if (!result.ok) {
      toast.push("error", result.error);
      return;
    }
    setData(result.data);
    setRef("");
    const labels: Record<string, string> = {
      target: "добавлен в целевые",
      exclude: "исключён",
      remove_target: "убран из целевых",
      remove_exclude: "убран из исключений",
    };
    toast.push("success", `Продавец ${labels[mode]}`);
    router.refresh();
  }

  const targets = data?.target_refs ?? [];
  const excludes = data?.exclude_refs ?? [];

  return (
    <section className="rounded-xl border border-neutral-800 bg-neutral-900/60 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center">
          <h2 className="text-base font-medium">Продавцы</h2>
          <InfoHint
            title="Целевые конкуренты"
            text="Добавьте продавцов по ссылке на профиль или по имени. Если задан список целевых — в медианы, дайджест и AI-модерацию идут только их объявления. Исключённые продавцы не учитываются никогда. Клик по имени продавца в выдаче фильтрует список."
          />
        </div>
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          className="rounded-lg border border-neutral-700 px-3 py-1 text-xs text-neutral-300 transition hover:border-neutral-500"
        >
          {open ? "Свернуть" : "Настроить"}
        </button>
      </div>

      {targets.length > 0 || excludes.length > 0 ? (
        <div className="mt-2 flex flex-wrap gap-2 text-xs">
          {targets.map((item) => (
            <span
              key={`t-${item}`}
              className="flex items-center gap-1 rounded-full border border-emerald-500/40 bg-emerald-500/10 px-2 py-0.5 text-emerald-200"
            >
              цель: {item}
              <button
                type="button"
                disabled={busy}
                onClick={() => apply(item, "remove_target")}
                className="text-emerald-300/80 hover:text-emerald-100"
              >
                ×
              </button>
            </span>
          ))}
          {excludes.map((item) => (
            <span
              key={`e-${item}`}
              className="flex items-center gap-1 rounded-full border border-red-500/40 bg-red-500/10 px-2 py-0.5 text-red-200"
            >
              минус: {item}
              <button
                type="button"
                disabled={busy}
                onClick={() => apply(item, "remove_exclude")}
                className="text-red-300/80 hover:text-red-100"
              >
                ×
              </button>
            </span>
          ))}
        </div>
      ) : (
        <p className="mt-1 text-xs text-neutral-500">
          Списки пусты — в статистике учитываются все продавцы выдачи.
        </p>
      )}

      {open ? (
        <div className="mt-3 flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <input
              value={ref}
              onChange={(event) => setRef(event.target.value)}
              placeholder="Ссылка на профиль или имя продавца"
              className="min-w-[240px] flex-1 rounded-lg border border-neutral-800 bg-neutral-950 px-3 py-1.5 text-sm text-neutral-200 outline-none focus:border-sky-500/60"
            />
            <button
              type="button"
              disabled={busy || !ref.trim()}
              onClick={() => apply(ref, "target")}
              className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-1.5 text-xs text-emerald-200 transition hover:bg-emerald-500/20 disabled:opacity-50"
            >
              В целевые
            </button>
            <button
              type="button"
              disabled={busy || !ref.trim()}
              onClick={() => apply(ref, "exclude")}
              className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-1.5 text-xs text-red-200 transition hover:bg-red-500/20 disabled:opacity-50"
            >
              Исключить
            </button>
          </div>
          {data && data.sellers.length > 0 ? (
            <ul className="flex max-h-64 flex-col gap-1 overflow-y-auto text-xs">
              {data.sellers.map((seller) => (
                <li
                  key={`${seller.seller_id}-${seller.url}`}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-neutral-800 bg-neutral-950/40 px-3 py-1.5"
                >
                  <span className="min-w-0 truncate text-neutral-300">
                    {seller.url ? (
                      <a
                        href={seller.url}
                        target="_blank"
                        rel="noreferrer"
                        className="hover:underline"
                      >
                        {seller.name || seller.url}
                      </a>
                    ) : (
                      seller.name || `Продавец ${seller.seller_id ?? "—"}`
                    )}
                    <span className="ml-2 text-neutral-500">{seller.count} шт.</span>
                  </span>
                  <span className="flex gap-1">
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => apply(seller.url || seller.name || "", "target")}
                      className="rounded border border-emerald-500/40 px-2 py-0.5 text-emerald-200 hover:bg-emerald-500/10"
                    >
                      цель
                    </button>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => apply(seller.url || seller.name || "", "exclude")}
                      className="rounded border border-red-500/40 px-2 py-0.5 text-red-200 hover:bg-red-500/10"
                    >
                      минус
                    </button>
                  </span>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
