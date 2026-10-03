"use client";

import { useState } from "react";

import { ackAlert, clearAlertsClient, type Alert } from "@/lib/api";
import { InfoHint } from "@/app/components/info-hint";
import { formatPercent, formatPrice, formatRelativeTime } from "@/lib/format";

function alertTitle(type: string): string {
  if (type === "price_above_market") {
    return "Наша цена выше рынка";
  }
  return type;
}

export function AlertsPanel({
  alerts,
  searchId,
}: {
  alerts: Alert[];
  searchId?: string;
}) {
  const [items, setItems] = useState(alerts);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [clearing, setClearing] = useState(false);

  if (items.length === 0) {
    return null;
  }

  async function dismiss(id: string) {
    setBusyId(id);
    const ok = await ackAlert(id);
    if (ok) {
      setItems((current) => current.filter((alert) => alert.id !== id));
    }
    setBusyId(null);
  }

  async function clearAll() {
    if (!window.confirm("Очистить все новые алерты? Действие необратимо.")) {
      return;
    }
    setClearing(true);
    const result = await clearAlertsClient({
      search_id: searchId ?? null,
      status: "new",
    });
    setClearing(false);
    if (result.ok) {
      setItems([]);
    }
  }

  return (
    <section className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center">
          <h2 className="text-lg font-medium text-amber-200">Алерты</h2>
          <InfoHint
            title="Правило алерта"
            text="Наша цена выше медианы сматченных конкурентов больше чем на настроенный порог (по умолчанию 10%). Повторные одинаковые алерты не дублируются: пока алерт не подтверждён, новый не создаётся. Очистить можно кнопкой — алерты удаляются из базы."
          />
        </div>
        <button
          type="button"
          onClick={clearAll}
          disabled={clearing}
          className="rounded-lg border border-amber-500/40 px-3 py-1 text-xs text-amber-200 transition hover:bg-amber-500/10 disabled:opacity-50"
        >
          {clearing ? "Очистка…" : "Очистить все"}
        </button>
      </div>
      <ul className="mt-4 flex flex-col gap-3">
        {items.map((alert) => {
          const payload = alert.payload ?? {};
          const deltaPct =
            typeof payload.delta_pct === "number" ? payload.delta_pct / 100 : null;
          const ourPrice =
            typeof payload.our_price === "number" ? payload.our_price : null;
          const marketMedian =
            typeof payload.market_median === "number" ? payload.market_median : null;
          return (
            <li
              key={alert.id}
              className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-amber-500/20 bg-neutral-900/60 px-4 py-3"
            >
              <div className="text-sm">
                <p className="font-medium text-amber-100">
                  {alertTitle(alert.type)}
                  <span className="ml-2 text-[11px] font-normal text-neutral-500">
                    {formatRelativeTime(alert.created_at)}
                  </span>
                </p>
                <p className="mt-0.5 text-neutral-400">
                  {String(payload.title ?? payload.sku ?? "")}
                  {ourPrice !== null ? ` · наша ${formatPrice(ourPrice)}` : ""}
                  {marketMedian !== null ? ` · медиана ${formatPrice(marketMedian)}` : ""}
                  {deltaPct !== null ? ` · +${formatPercent(deltaPct)}` : ""}
                </p>
              </div>
              <button
                type="button"
                onClick={() => dismiss(alert.id)}
                disabled={busyId === alert.id}
                className="rounded-lg border border-neutral-700 px-3 py-1.5 text-xs text-neutral-300 transition hover:border-neutral-500 disabled:opacity-50"
              >
                {busyId === alert.id ? "…" : "Принять"}
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
