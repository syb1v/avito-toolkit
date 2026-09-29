"use client";

import { useState } from "react";

import { createDigest, type Digest } from "@/lib/api";

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

  async function generate() {
    setLoading(true);
    setError(null);
    const result = await createDigest(searchId);
    if (result.digest) {
      setDigest(result.digest);
    } else {
      setError(result.error ?? "Неизвестная ошибка");
    }
    setLoading(false);
  }

  return (
    <div className="rounded-xl border border-neutral-800 bg-neutral-900/60 p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-medium">AI-дайджест рынка</h2>
          <p className="mt-1 text-xs text-neutral-500">
            Сводка через LLM (litellm): цены, спрос, рекомендации действий
          </p>
        </div>
        <button
          type="button"
          onClick={generate}
          disabled={loading}
          className="rounded-lg border border-emerald-500/40 bg-emerald-500/15 px-4 py-2 text-sm text-emerald-200 transition hover:bg-emerald-500/25 disabled:opacity-50"
        >
          {loading ? "Генерация…" : "Сгенерировать"}
        </button>
      </div>

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
