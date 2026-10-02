"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

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
  const [busy, setBusy] = useState(false);

  async function clear() {
    if (!window.confirm("Очистить алерты? Действие необратимо.")) {
      return;
    }
    setBusy(true);
    const result = await clearAlertsClient({
      search_id: searchId ?? null,
      status,
    });
    setBusy(false);
    if (result.ok) {
      router.refresh();
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
