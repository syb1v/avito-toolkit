"use client";

import { useCallback, useEffect, useState } from "react";

import {
  createManualEditClient,
  editActionClient,
  fetchEditsClient,
  type ListingEdit,
} from "@/lib/api";
import { useToast } from "@/app/components/toast";
import { formatPercent, formatPrice } from "@/lib/format";

const STATUS_LABELS: Record<string, string> = {
  draft: "черновик",
  approved: "одобрено",
  applying: "применяется",
  applied: "применено",
  reverting: "откат",
  reverted: "откачено",
  rejected: "отклонено",
  failed: "ошибка",
};

const STATUS_STYLES: Record<string, string> = {
  draft: "border-amber-500/30 bg-amber-500/10 text-amber-200",
  approved: "border-sky-500/30 bg-sky-500/10 text-sky-200",
  applied: "border-emerald-500/30 bg-emerald-500/15 text-emerald-300",
  rejected: "border-neutral-700 bg-neutral-800 text-neutral-400",
  reverted: "border-neutral-700 bg-neutral-800 text-neutral-300",
  failed: "border-red-500/30 bg-red-500/10 text-red-300",
};

export function SkuEdits({ sku }: { sku: string }) {
  const [items, setItems] = useState<ListingEdit[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [manualPrice, setManualPrice] = useState("");
  const toast = useToast();

  const load = useCallback(async () => {
    const data = await fetchEditsClient(sku);
    setItems(data?.items ?? []);
  }, [sku]);

  useEffect(() => {
    load();
  }, [load]);

  async function act(edit: ListingEdit, action: "approve" | "reject" | "apply" | "revert") {
    setBusy(true);
    const result = await editActionClient(edit.id, action);
    setBusy(false);
    if (!result.ok) {
      toast.push("error", result.error);
    } else {
      const labels: Record<string, string> = {
        approve: "подтверждена",
        reject: "отклонена",
        apply: "применяется",
        revert: "откатывается",
      };
      toast.push("success", `Правка ${labels[action] ?? action}`);
      await load();
    }
  }

  async function submitManual() {
    const value = Number(manualPrice.replace(/\s/g, "").replace(",", "."));
    if (!Number.isFinite(value) || value <= 0) {
      toast.push("error", "Укажите цену числом");
      return;
    }
    setBusy(true);
    const result = await createManualEditClient(sku, value);
    setBusy(false);
    if (!result.ok) {
      toast.push("error", result.error);
      return;
    }
    setManualPrice("");
    toast.push(
      "success",
      result.data.applied
        ? "Своя цена создана и поставлена в очередь применения"
        : "Своя цена сохранена черновиком — нужно подтверждение",
    );
    await load();
  }

  if (items === null) {
    return <p className="text-xs text-neutral-600">Правки загружаются…</p>;
  }
  if (items.length === 0) {
    return <p className="text-xs text-neutral-600">Правок ещё не было</p>;
  }

  const latest = items[0];
  return (
    <div className="flex flex-col gap-1.5 rounded-lg border border-neutral-800 bg-neutral-950/40 p-2.5">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span
          className={`rounded-full border px-2 py-0.5 ${
            STATUS_STYLES[latest.status] ?? "border-neutral-700 bg-neutral-800 text-neutral-300"
          }`}
        >
          {STATUS_LABELS[latest.status] ?? latest.status}
        </span>
        <span className="tabular-nums text-neutral-300">
          {formatPrice(latest.old_price)} → {formatPrice(latest.target_price)}
        </span>
        <span className="text-neutral-500">
          {latest.delta_pct > 0 ? "+" : ""}
          {formatPercent(latest.delta_pct / 100)} · {latest.mode}
        </span>
      </div>
      {latest.ai_summary ? (
        <p className="text-xs text-neutral-400">{latest.ai_summary}</p>
      ) : null}
      {latest.error ? (
        <p className="text-xs text-red-300/90">{latest.error}</p>
      ) : null}
      <div className="flex flex-wrap gap-2">
        {latest.status === "draft" ? (
          <>
            <button
              type="button"
              disabled={busy}
              onClick={() => act(latest, "approve")}
              className="rounded-lg border border-sky-500/40 bg-sky-500/10 px-2.5 py-1 text-xs text-sky-200 transition hover:bg-sky-500/20 disabled:opacity-50"
            >
              Подтвердить
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => act(latest, "reject")}
              className="rounded-lg border border-neutral-700 px-2.5 py-1 text-xs text-neutral-300 transition hover:border-neutral-500 disabled:opacity-50"
            >
              Отклонить
            </button>
          </>
        ) : null}
        {latest.status === "approved" ? (
          <button
            type="button"
            disabled={busy}
            onClick={() => act(latest, "apply")}
            className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-2.5 py-1 text-xs text-emerald-200 transition hover:bg-emerald-500/20 disabled:opacity-50"
          >
            Применить сейчас
          </button>
        ) : null}
        {latest.status === "applied" ? (
          <button
            type="button"
            disabled={busy}
            onClick={() => act(latest, "revert")}
            className="rounded-lg border border-neutral-700 px-2.5 py-1 text-xs text-neutral-300 transition hover:border-neutral-500 disabled:opacity-50"
          >
            Откатить
          </button>
        ) : null}
        {items.length > 1 ? (
          <span className="self-center text-xs text-neutral-600">
            всего правок: {items.length}
          </span>
        ) : null}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <input
          value={manualPrice}
          onChange={(event) => setManualPrice(event.target.value)}
          placeholder="своя цена, ₽"
          inputMode="numeric"
          className="w-32 rounded border border-neutral-800 bg-neutral-950 px-2 py-1 text-xs text-neutral-200 outline-none focus:border-sky-500/60"
        />
        <button
          type="button"
          disabled={busy || !manualPrice.trim()}
          onClick={submitManual}
          className="rounded-lg border border-violet-500/40 bg-violet-500/10 px-2.5 py-1 text-xs text-violet-200 transition hover:bg-violet-500/20 disabled:opacity-50"
        >
          Поставить свою цену
        </button>
      </div>
    </div>
  );
}
