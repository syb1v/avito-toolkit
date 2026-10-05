"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { useConfirm } from "@/app/components/confirm";
import { useToast } from "@/app/components/toast";
import { clearAlertsClient } from "@/lib/api";

export function ClearAlertsButton({
  searchId,
  status = "new",
  label = "Очистить",
  className,
}: {
  searchId?: string;
  status?: string;
  label?: string;
  className?: string;
}) {
  const router = useRouter();
  const toast = useToast();
  const confirm = useConfirm();
  const [busy, setBusy] = useState(false);

  async function clear() {
    const ok = await confirm({
      title: "Очистить алерты?",
      text: "Удалить выбранные алерты? Действие необратимо.",
      confirmLabel: "Очистить",
      danger: true,
    });
    if (!ok) {
      return;
    }
    setBusy(true);
    const result = await clearAlertsClient({
      search_id: searchId ?? null,
      status,
    });
    setBusy(false);
    if (result.ok) {
      toast.push("success", `Очищено алертов: ${result.data?.deleted ?? 0}`);
      router.refresh();
    } else {
      toast.push("error", result.error);
    }
  }

  return (
    <button
      type="button"
      onClick={clear}
      disabled={busy}
      className={
        className ??
        "rounded-lg border border-neutral-700 px-3 py-1 text-xs text-neutral-300 transition hover:border-neutral-500 disabled:opacity-50"
      }
    >
      {busy ? "Очистка…" : label}
    </button>
  );
}
