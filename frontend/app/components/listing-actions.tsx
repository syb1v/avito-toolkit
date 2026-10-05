"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { useToast } from "@/app/components/toast";
import { setListingsExcludedClient } from "@/lib/api";

export function ListingActions({
  searchId,
  listingId,
  manualExcluded,
}: {
  searchId: string;
  listingId: number;
  manualExcluded: boolean;
}) {
  const router = useRouter();
  const toast = useToast();
  const [busy, setBusy] = useState(false);

  async function toggle() {
    setBusy(true);
    const result = await setListingsExcludedClient(
      searchId,
      [listingId],
      !manualExcluded,
      "вручную",
    );
    setBusy(false);
    if (result.ok) {
      toast.push(
        "success",
        manualExcluded ? "Объявление возвращено в расчёт" : "Объявление скрыто из расчёта",
      );
      router.refresh();
    } else {
      toast.push("error", result.error);
    }
  }

  return (
    <button
      type="button"
      onClick={toggle}
      disabled={busy}
      title={
        manualExcluded
          ? "Вернуть объявление в расчёт цен"
          : "Убрать объявление из расчёта цен (останется в выдаче)"
      }
      className={`whitespace-nowrap rounded-lg border px-2 py-1 text-[11px] transition disabled:opacity-50 ${
        manualExcluded
          ? "border-emerald-500/40 text-emerald-300 hover:bg-emerald-500/10"
          : "border-neutral-700 text-neutral-300 hover:border-neutral-500"
      }`}
    >
      {busy ? "…" : manualExcluded ? "Вернуть" : "Скрыть"}
    </button>
  );
}
