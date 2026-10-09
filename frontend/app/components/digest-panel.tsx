"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  applyDigestSuggestions,
  createDigest,
  fetchDigestClient,
  type Digest,
} from "@/lib/api";
import { useConfirm } from "@/app/components/confirm";
import { useToast } from "@/app/components/toast";
import { formatPrice, formatRelativeTime } from "@/lib/format";
import { InfoHint } from "@/app/components/info-hint";
import { useEvents } from "@/lib/events";

const DEMAND_LABELS: Record<string, string> = {
  weak: "слабый спрос",
  balanced: "сбалансированный спрос",
  strong: "высокий спрос",
};

const DEMAND_STYLES: Record<string, string> = {
  weak: "border-red-500/30 bg-red-500/10 text-red-300",
  balanced: "border-blue-500/30 bg-blue-500/10 text-blue-300",
  strong: "border-emerald-500/30 bg-emerald-500/15 text-emerald-300",
};

export function DigestPanel({ searchId }: { searchId: string }) {
  const [digest, setDigest] = useState<Digest | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [applying, setApplying] = useState(false);
  const toast = useToast();
  const confirm = useConfirm();

  useEffect(() => {
    let cancelled = false;
    fetchDigestClient(searchId).then((latest) => {
      if (!cancelled && latest) {
        setDigest(latest);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [searchId]);

  useEffect(() => {
    if (!loading) {
      return;
    }
    setElapsed(0);
    const timer = setInterval(() => setElapsed((value) => value + 1), 1000);
    return () => clearInterval(timer);
  }, [loading]);

  useEvents(
    (event) => {
      fetchDigestClient(searchId).then((latest) => {
        if (latest) {
          setDigest(latest);
        }
      });
    },
    (event) => event.type === "digest.new" && event.payload.search_id === searchId,
  );

  async function applySuggestions() {
    if (!digest) {
      return;
    }
    const ok = await confirm({
      title: "Создать черновики правок?",
      text: `AI предложил цены для ${digest.price_suggestions.length} наших товаров. Правки появятся на странице «Правки»: шаг ограничен настройкой, крупные изменения уйдут на подтверждение.`,
      confirmLabel: "Создать",
    });
    if (!ok) {
      return;
    }
    setApplying(true);
    const result = await applyDigestSuggestions(searchId);
    setApplying(false);
    if (result === null) {
      toast.push("error", "Не удалось создать правки");
      return;
    }
    toast.push(
      "success",
      `Черновиков создано: ${result.created}${
        result.skipped > 0 ? `, пропущено: ${result.skipped}` : ""
      }`,
    );
    const createdSkus = new Set(result.skus);
    setDigest((current) =>
      current === null
        ? current
        : {
            ...current,
            price_suggestions: current.price_suggestions.filter(
              (item) => !createdSkus.has(item.sku),
            ),
          },
    );
  }

  async function generate() {
    setLoading(true);
    setError(null);
    const result = await createDigest(searchId);
    if (result.digest) {
      setDigest(result.digest);
      toast.push("success", "Дайджест обновлён и сохранён — увидят все");
    } else {
      setError(result.error ?? "Неизвестная ошибка");
      toast.push("error", result.error ?? "Не удалось сгенерировать дайджест");
    }
    setLoading(false);
  }

  return (
    <div className="rounded-xl border border-neutral-800 bg-neutral-900/60 p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center">
            <h2 className="text-lg font-medium">AI-дайджест рынка</h2>
            <InfoHint
              title="Что внутри"
              text="LLM (DeepSeek) получает метрики поиска: цены после IQR-фильтрации, вымывание, активность и топ выдачи, и возвращает сводку строго по этим данным. Модель, токены и стоимость видны под ответом. Нужен ключ DEEPSEEK_API_KEY."
            />
          </div>
          <p className="mt-1 text-xs text-neutral-500">
            Сводка через LLM: цены, спрос, рекомендации. Сохраняется в базе — все
            видят последнюю версию, повторно генерировать не нужно.
            {digest?.created_at
              ? ` Обновлён ${formatRelativeTime(digest.created_at)}.`
              : ""}
          </p>
        </div>
        <button
          type="button"
          onClick={generate}
          disabled={loading}
          className="w-full rounded-lg border border-emerald-500/40 bg-emerald-500/15 px-4 py-2 text-sm text-emerald-200 transition hover:bg-emerald-500/25 disabled:opacity-50 sm:w-auto"
        >
          {loading ? "Генерация…" : digest ? "Обновить" : "Сгенерировать"}
        </button>
      </div>

      {loading ? (
        <div className="mt-4">
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-neutral-800">
            <div className="h-full w-1/3 animate-pulse rounded-full bg-emerald-500/70" />
          </div>
          <p className="mt-2 text-xs text-neutral-500">
            Запрос к {`DeepSeek`}… прошло {elapsed} с (обычно 5–30 с)
          </p>
        </div>
      ) : null}

      {error ? (
        <p className="mt-4 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-200">
          {error}
          {error.includes("DEEPSEEK_API_KEY") ? (
            <span className="block text-xs text-amber-300/80">
              Задайте ключ в .env (DEEPSEEK_API_KEY) и перезапустите backend.
            </span>
          ) : null}
        </p>
      ) : null}

      {digest ? (
        <div className="mt-5 flex flex-col gap-4">
          <div className="flex flex-wrap items-center gap-3">
            <p className="text-base font-medium">{digest.headline}</p>
            <span
              className={`rounded-full border px-3 py-1 text-xs ${
                DEMAND_STYLES[digest.demand_signal] ??
                "border-neutral-700 bg-neutral-800 text-neutral-300"
              }`}
            >
              {DEMAND_LABELS[digest.demand_signal] ?? digest.demand_signal}
            </span>
          </div>
          <p className="text-sm text-neutral-400">{digest.price_range_comment}</p>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <p className="text-xs uppercase tracking-wider text-neutral-500">
                Конкуренты
              </p>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-neutral-300">
                {digest.competitor_notes.map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wider text-neutral-500">
                Рекомендации
              </p>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-neutral-300">
                {digest.recommended_actions.map((action) => (
                  <li key={action}>{action}</li>
                ))}
              </ul>
            </div>
          </div>
          {digest.price_suggestions.length > 0 ? (
            <div className="rounded-lg border border-sky-500/25 bg-sky-500/5 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-xs uppercase tracking-wider text-sky-300/80">
                  AI-предложения по нашим ценам
                </p>
                <button
                  type="button"
                  onClick={applySuggestions}
                  disabled={applying}
                  className="rounded-lg border border-sky-500/40 bg-sky-500/15 px-3 py-1.5 text-xs text-sky-200 transition hover:bg-sky-500/25 disabled:opacity-50"
                >
                  {applying ? "Создание…" : "Создать черновики правок"}
                </button>
              </div>
              <ul className="mt-2 flex flex-col gap-1.5 text-sm text-neutral-300">
                {digest.price_suggestions.map((item) => (
                  <li key={item.sku} className="flex flex-wrap gap-x-2">
                    <span className="font-medium">{item.sku}</span>
                    <span className="text-sky-200">
                      → {formatPrice(item.target_price)}
                    </span>
                    <span className="text-neutral-500">{item.reason}</span>
                  </li>
                ))}
              </ul>
              <p className="mt-2 text-xs text-neutral-500">
                Правки с подтверждением — на странице{" "}
                <Link href="/edits" className="text-sky-300 underline">
                  «Правки»
                </Link>
                .
              </p>
            </div>
          ) : null}
          <p className="text-xs text-neutral-600">
            {digest.model}
            {digest.tokens_in !== null || digest.tokens_out !== null
              ? ` · токены ${digest.tokens_in ?? "—"}/${digest.tokens_out ?? "—"}`
              : ""}
            {digest.cost_usd !== null ? ` · $${digest.cost_usd.toFixed(4)}` : ""}
          </p>
        </div>
      ) : null}
    </div>
  );
}
