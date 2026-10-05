"use client";

import { useCallback, useEffect, useState } from "react";

import { useConfirm } from "@/app/components/confirm";
import { InfoHint } from "@/app/components/info-hint";
import { useToast } from "@/app/components/toast";
import {
  createEditsClient,
  editActionClient,
  fetchEditsClient,
  type EditsList,
  type ListingEdit,
} from "@/lib/api";
import { formatPercent, formatPrice } from "@/lib/format";

const STATUS_META: Record<string, { label: string; className: string }> = {
  draft: { label: "нужно одобрить", className: "border-amber-500/40 bg-amber-500/10 text-amber-200" },
  approved: { label: "одобрено", className: "border-sky-500/40 bg-sky-500/10 text-sky-200" },
  applying: { label: "применяется…", className: "border-sky-500/40 bg-sky-500/10 text-sky-200" },
  applied: { label: "применено", className: "border-emerald-500/40 bg-emerald-500/15 text-emerald-200" },
  reverting: { label: "откат…", className: "border-sky-500/40 bg-sky-500/10 text-sky-200" },
  reverted: { label: "откачено", className: "border-neutral-600 bg-neutral-800 text-neutral-300" },
  rejected: { label: "отклонено", className: "border-neutral-700 bg-neutral-800 text-neutral-400" },
  failed: { label: "ошибка", className: "border-red-500/40 bg-red-500/10 text-red-200" },
};

export function EditsPanel({ initial }: { initial: EditsList }) {
  const [data, setData] = useState(initial);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const toast = useToast();
  const confirm = useConfirm();

  const refresh = useCallback(async () => {
    const fresh = await fetchEditsClient();
    if (fresh) {
      setData(fresh);
    }
  }, []);

  const hasActive = data.items.some(
    (item) => item.status === "applying" || item.status === "reverting",
  );

  useEffect(() => {
    if (!hasActive) {
      return;
    }
    const timer = setInterval(refresh, 5000);
    return () => clearInterval(timer);
  }, [hasActive, refresh]);

  async function createDrafts() {
    setCreating(true);
    const result = await createEditsClient({ max_items: 10 });
    setCreating(false);
    if (!result.ok) {
      toast.push("error", result.error);
      return;
    }
    toast.push(
      "success",
      result.data.created > 0
        ? `Создано черновиков: ${result.data.created}`
        : "Нет новых рекомендаций (нужны матчи с рынком и актуальные цены)",
    );
    await refresh();
  }

  async function act(edit: ListingEdit, action: "approve" | "reject" | "apply" | "revert") {
    if (action === "apply") {
      const message =
        edit.mode === "live"
          ? `Применить цену ${formatPrice(edit.target_price)} для «${edit.sku}» через кабинет продавца?`
          : `Отметить правку «${edit.sku}» как применённую (режим dry-run, цена на Авито не меняется)?`;
      const ok = await confirm({
        title: "Применить правку?",
        text: message,
        confirmLabel: "Применить",
      });
      if (!ok) {
        return;
      }
    }
    setBusyId(edit.id);
    const result = await editActionClient(edit.id, action);
    setBusyId(null);
    if (!result.ok) {
      toast.push("error", result.error);
      return;
    }
    const labels = {
      approve: "Правка одобрена",
      reject: "Правка отклонена",
      apply: "Правка поставлена в очередь",
      revert: "Откат поставлен в очередь",
    } as const;
    toast.push("success", labels[action]);
    await refresh();
  }

  const button =
    "rounded-lg border px-2.5 py-1 text-xs transition disabled:opacity-50";

  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center">
          <h2 className="text-lg font-medium">Правки объявлений</h2>
          <InfoHint
            title="Как это работает"
            text="Мы сравниваем ваши цены с рынком и предлагаем новую цену. Шаг ограничен 5%, при изменении больше 10% правку нужно одобрить вручную. В режиме dry-run всё фиксируется в журнале, но на Авито ничего не меняется. В режиме live правка выполняется в вашем кабинете продавца через браузер: мы открываем объявление, меняем цену, сохраняем и проверяем результат — с скриншотом и возможностью отката. API Авито для этого не используется."
          />
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <span
            className={`rounded-full border px-3 py-1 text-xs ${
              data.live_edits
                ? "border-red-500/40 bg-red-500/10 text-red-200"
                : "border-neutral-700 bg-neutral-800 text-neutral-300"
            }`}
          >
            режим: {data.live_edits ? "live (меняем на Авито)" : "dry-run (только журнал)"}
          </span>
          <button
            type="button"
            onClick={createDrafts}
            disabled={creating}
            className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-1.5 text-xs text-emerald-200 transition hover:bg-emerald-500/20 disabled:opacity-50"
          >
            {creating ? "Считаю…" : "Сформировать черновики"}
          </button>
        </div>
      </div>

      {data.items.length === 0 ? (
        <div className="rounded-xl border border-dashed border-neutral-800 p-6 text-sm text-neutral-400">
          <p className="text-neutral-200">Правок пока нет.</p>
          <p className="mt-1">
            Нажмите «Сформировать черновики» — система возьмёт рекомендации по вашим
            SKU и создаст план изменений. Ничего не применится без вашего нажатия.
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-neutral-800">
          <table className="w-full min-w-[820px] text-sm">
            <thead>
              <tr className="border-b border-neutral-800 text-left text-xs uppercase tracking-wider text-neutral-500">
                <th className="px-4 py-3 font-medium">SKU</th>
                <th className="px-4 py-3 text-right font-medium">Сейчас</th>
                <th className="px-4 py-3 text-right font-medium">Цель</th>
                <th className="px-4 py-3 text-right font-medium">Δ</th>
                <th className="px-4 py-3 font-medium">Статус</th>
                <th className="px-4 py-3 text-right font-medium">Действия</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-800">
              {data.items.map((edit) => {
                const meta = STATUS_META[edit.status] ?? {
                  label: edit.status,
                  className: "border-neutral-700 bg-neutral-800 text-neutral-300",
                };
                return (
                  <tr key={edit.id} className="align-top hover:bg-neutral-900/60">
                    <td className="max-w-[280px] px-4 py-3">
                      <p className="line-clamp-1 font-medium" title={edit.title ?? edit.sku}>
                        {edit.title ?? edit.sku}
                      </p>
                      <p className="text-xs text-neutral-500">
                        {edit.sku} · {edit.strategy}
                      </p>
                      {edit.error ? (
                        <p className="mt-1 text-xs text-red-300/90" title={edit.error}>
                          {edit.error}
                        </p>
                      ) : null}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">
                      {formatPrice(edit.old_price)}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">
                      {formatPrice(edit.target_price)}
                    </td>
                    <td
                      className={`px-4 py-3 text-right tabular-nums ${
                        edit.delta_pct < 0 ? "text-emerald-300" : "text-amber-300"
                      }`}
                    >
                      {edit.delta_pct > 0 ? "+" : ""}
                      {formatPercent(edit.delta_pct / 100)}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`rounded-full border px-2 py-0.5 text-[11px] ${meta.className}`}>
                        {meta.label}
                      </span>
                      <p className="mt-1 text-[10px] text-neutral-600">{edit.mode}</p>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap justify-end gap-1.5">
                        {edit.status === "draft" ? (
                          <>
                            <button
                              type="button"
                              onClick={() => act(edit, "approve")}
                              disabled={busyId === edit.id}
                              className={`${button} border-sky-500/40 text-sky-200 hover:bg-sky-500/10`}
                            >
                              Одобрить
                            </button>
                            <button
                              type="button"
                              onClick={() => act(edit, "reject")}
                              disabled={busyId === edit.id}
                              className={`${button} border-neutral-700 text-neutral-300 hover:border-neutral-500`}
                            >
                              Отклонить
                            </button>
                          </>
                        ) : null}
                        {edit.status === "approved" ? (
                          <>
                            <button
                              type="button"
                              onClick={() => act(edit, "apply")}
                              disabled={busyId === edit.id}
                              className={`${button} border-emerald-500/40 text-emerald-200 hover:bg-emerald-500/10`}
                            >
                              {edit.mode === "live" ? "Применить" : "Отметить"}
                            </button>
                            <button
                              type="button"
                              onClick={() => act(edit, "reject")}
                              disabled={busyId === edit.id}
                              className={`${button} border-neutral-700 text-neutral-300 hover:border-neutral-500`}
                            >
                              Отклонить
                            </button>
                          </>
                        ) : null}
                        {edit.status === "applied" || edit.status === "dry_run" ? (
                          <button
                            type="button"
                            onClick={() => act(edit, "revert")}
                            disabled={busyId === edit.id}
                            className={`${button} border-amber-500/40 text-amber-200 hover:bg-amber-500/10`}
                          >
                            Откатить
                          </button>
                        ) : null}
                        {edit.status === "failed" ? (
                          <button
                            type="button"
                            onClick={() => act(edit, "apply")}
                            disabled={busyId === edit.id}
                            className={`${button} border-neutral-700 text-neutral-300 hover:border-neutral-500`}
                          >
                            Повторить
                          </button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-xs text-neutral-600">
        Журнал хранит цену до/после, статус, ошибки и скриншот выполнения (на сервере,
        каталог «edits» рядом с профилем продавца). Откат возвращает прежнюю цену тем
        же путём.
      </p>
    </section>
  );
}
