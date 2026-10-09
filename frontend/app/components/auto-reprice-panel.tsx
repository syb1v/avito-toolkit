"use client";

import { useEffect, useState } from "react";

import {
  fetchAutoRepriceClient,
  patchAutoRepriceClient,
  type AutoRepriceState,
} from "@/lib/api";
import { useConfirm } from "@/app/components/confirm";
import { useToast } from "@/app/components/toast";
import { InfoHint } from "@/app/components/info-hint";
import { formatRelativeTime } from "@/lib/format";
import { EDIT_STATUS_LABELS as STATUS_LABELS } from "@/lib/terms";

export function AutoRepricePanel() {
  const [state, setState] = useState<AutoRepriceState | null>(null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const confirm = useConfirm();

  useEffect(() => {
    let cancelled = false;
    fetchAutoRepriceClient().then((data) => {
      if (!cancelled) {
        setState(data);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  async function patch(payload: { enabled?: boolean; live?: boolean }) {
    setBusy(true);
    const result = await patchAutoRepriceClient(payload);
    setBusy(false);
    if (!result.ok) {
      toast.push("error", result.error);
      return;
    }
    setState(result.data);
    toast.push(
      "success",
      `Авто-правки: ${result.data.enabled ? "включены" : "выключены"} (${result.data.mode_effective})`,
    );
  }

  async function enableLive() {
    const ok = await confirm({
      title: "Включить боевой режим?",
      text: "Ночное задание будет реально менять цены на Авито в пределах ±5% и не ниже себестоимости. Откат доступен в карточке каждого SKU.",
      confirmLabel: "Включить live",
      danger: true,
    });
    if (ok) {
      await patch({ live: true });
    }
  }

  const last = state?.last;

  return (
    <section className="rounded-xl border border-neutral-800 bg-neutral-900/60 p-4 sm:p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-base font-medium sm:text-lg">Авто-правки цен</h2>
          <InfoHint
            title="Как работают авто-правки"
            text="Раз в сутки ночью система пересчитывает рекомендации по всем SKU (шаг ≤5%, не ниже себестоимости) и меняет цены в кабинете продавца. Изменения больше порога ждут подтверждения в карточке SKU. В dry-run ничего не меняется — только журнал."
          />
          {state ? (
            <span
              className={`rounded-full border px-2.5 py-0.5 text-xs ${
                !state.enabled
                  ? "border-neutral-700 bg-neutral-800 text-neutral-400"
                  : state.mode_effective === "live"
                    ? "border-red-500/40 bg-red-500/10 text-red-200"
                    : "border-sky-500/30 bg-sky-500/10 text-sky-200"
              }`}
            >
              {!state.enabled
                ? "выключены"
                : state.mode_effective === "live"
                  ? "live — меняем на Авито"
                  : "dry-run"}
            </span>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {state ? (
            <span className="text-xs text-neutral-500">
              следующий прогон: {formatRelativeTime(state.next_run_at)}
            </span>
          ) : null}
          <button
            type="button"
            disabled={busy || !state}
            onClick={() => patch({ enabled: !state?.enabled })}
            className={`rounded-lg border px-3 py-1.5 text-xs transition disabled:opacity-50 ${
              state?.enabled
                ? "border-amber-500/40 bg-amber-500/10 text-amber-200 hover:bg-amber-500/20"
                : "border-emerald-500/40 bg-emerald-500/10 text-emerald-200 hover:bg-emerald-500/20"
            }`}
          >
            {state?.enabled ? "Выключить" : "Включить"}
          </button>
          {state?.enabled && state.mode_effective === "dry_run" ? (
            <button
              type="button"
              disabled={busy || !state.live_allowed}
              onClick={enableLive}
              title={
                state.live_allowed
                  ? "Реально менять цены на Авито"
                  : "Запрещено: в .env SELLER_EDIT_MODE=dry_run"
              }
              className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-1.5 text-xs text-red-200 transition hover:bg-red-500/20 disabled:opacity-50"
            >
              Боевой режим
            </button>
          ) : null}
        </div>
      </div>

      {last ? (
        <div className="mt-3 rounded-lg border border-neutral-800 bg-neutral-950/40 p-3">
          <p className="text-sm text-neutral-200">
            {last.headline || "Ночной прогон"} ·{" "}
            <span className="text-xs text-neutral-500">
              {formatRelativeTime(last.at)} · создано {last.created}, применено{" "}
              {last.applied}
              {last.drafts > 0 ? `, черновиков ${last.drafts}` : ""}
              {last.failed > 0 ? `, ошибок ${last.failed}` : ""}
            </span>
          </p>
          {last.items.length > 0 ? (
            <ul className="mt-2 flex flex-col gap-1.5 text-xs text-neutral-400">
              {last.items.slice(0, 5).map((item) => (
                <li key={item.sku} className="flex flex-wrap gap-x-2">
                  <span className="font-mono text-neutral-500">{item.sku}</span>
                  <span className="tabular-nums">
                    {item.old_price.toFixed(0)} → {item.target_price.toFixed(0)} ₽
                  </span>
                  <span className="text-neutral-500">
                    {STATUS_LABELS[item.status] ?? item.status}
                  </span>
                  {item.reason ? <span>— {item.reason}</span> : null}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : (
        <p className="mt-3 text-xs text-neutral-500">
          Ночных прогонов пока не было. Включите тумблер — первое применение
          произойдёт по расписанию (обычно 03:00 МСК).
        </p>
      )}
    </section>
  );
}
