"use client";

import { useEffect, useState } from "react";

import { fetchProgressClient, type SearchProgress } from "@/lib/api";

const META: Record<string, { label: string; className: string }> = {
  idle: { label: "не запускался", className: "border-neutral-700 bg-neutral-800 text-neutral-400" },
  queued: { label: "в очереди", className: "border-amber-500/30 bg-amber-500/10 text-amber-200" },
  running: { label: "обход идёт", className: "border-sky-500/30 bg-sky-500/10 text-sky-200" },
  done: { label: "обход завершён", className: "border-emerald-500/30 bg-emerald-500/15 text-emerald-300" },
  failed: { label: "ошибка обхода", className: "border-red-500/30 bg-red-500/10 text-red-300" },
};

export function SearchStatusBadge({ searchId, active }: { searchId: string; active: boolean }) {
  const [progress, setProgress] = useState<SearchProgress | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      const next = await fetchProgressClient(searchId);
      if (!cancelled) setProgress(next);
    };
    void load();
    const timer = window.setInterval(load, 15000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [searchId]);

  const crawl = progress?.status ?? "idle";
  const meta = META[crawl] ?? META.idle;
  return (
    <div className="flex flex-wrap justify-end gap-1.5">
      <span className={`whitespace-nowrap rounded-full border px-2 py-0.5 text-[10px] ${active ? "border-emerald-500/30 bg-emerald-500/15 text-emerald-300" : "border-neutral-700 bg-neutral-800 text-neutral-400"}`}>
        {active ? "по расписанию" : "пауза"}
      </span>
      <span className={`whitespace-nowrap rounded-full border px-2 py-0.5 text-[10px] ${meta.className}`}>
        {meta.label}
      </span>
    </div>
  );
}
