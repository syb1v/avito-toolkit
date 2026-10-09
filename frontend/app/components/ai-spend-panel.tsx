"use client";

import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { fetchAiBalanceClient, type AiBalance, type Dashboard } from "@/lib/api";
import { formatRelativeTime } from "@/lib/format";
import { AI_TASK_LABELS } from "@/lib/terms";

type Spend = Dashboard["ai_spend"];

function usd(value: number, digits = 4): string {
  return `$${value.toFixed(digits)}`;
}

export function AiSpendPanel({ initial }: { initial?: Spend }) {
  const [balance, setBalance] = useState<AiBalance | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchAiBalanceClient().then((data) => {
      if (!cancelled) {
        setBalance(data);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!initial) {
    return null;
  }

  const avg = initial.avg_day_7d > 0 ? initial.avg_day_7d : initial.avg_day_30d;
  const forecast = avg * 30;
  const runway =
    balance?.balance != null && avg > 0 ? Math.floor(balance.balance / avg) : null;
  const chartData = initial.daily.slice(-14);

  return (
    <section className="rounded-xl border border-neutral-800 bg-neutral-900/60 p-4 sm:p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-base font-medium sm:text-lg">Расходы на AI</h2>
          <span className="rounded-full border border-violet-500/30 bg-violet-500/10 px-2.5 py-0.5 text-xs text-violet-200">
            за 30 дней {usd(initial.month_usd)}
          </span>
          {balance?.configured ? (
            <span
              className={`rounded-full border px-2.5 py-0.5 text-xs ${
                balance.low || (balance.balance ?? 1) <= 0
                  ? "border-amber-500/40 bg-amber-500/10 text-amber-200"
                  : "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
              }`}
              title={balance.reason}
            >
              баланс {balance.balance != null ? usd(balance.balance, 2) : "—"}
              {balance.currency ? ` ${balance.currency}` : ""}
              {balance.updated_at
                ? ` · ${formatRelativeTime(balance.updated_at)}`
                : ""}
            </span>
          ) : null}
        </div>
        <span className="text-xs text-neutral-500">
          за сутки {usd(initial.day_usd)} · всего {usd(initial.total_usd)}
        </span>
      </div>

      {balance?.configured && balance.low ? (
        <p className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/10 p-2.5 text-xs text-amber-200">
          {balance.reason || "Баланс AI API на исходе — пополните ключ."}
        </p>
      ) : null}

      <div className="mt-4 grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <div>
          <p className="text-xs uppercase tracking-wider text-neutral-500">
            Расход по дням (14 дней)
          </p>
          <div className="mt-2 h-40 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                <CartesianGrid stroke="#262626" strokeDasharray="3 3" vertical={false} />
                <XAxis
                  dataKey="date"
                  stroke="#737373"
                  fontSize={10}
                  tickLine={false}
                  tickFormatter={(value: string) => value.slice(5)}
                />
                <YAxis
                  stroke="#737373"
                  fontSize={10}
                  tickLine={false}
                  width={52}
                  tickFormatter={(value) => usd(Number(value), 3)}
                />
                <Tooltip
                  contentStyle={{
                    background: "#171717",
                    border: "1px solid #404040",
                    borderRadius: 8,
                    fontSize: 12,
                  }}
                  formatter={(value) => [usd(Number(value)), "расход"]}
                />
                <Bar dataKey="cost_usd" fill="#8b5cf6" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="flex flex-col gap-2">
          <p className="text-xs uppercase tracking-wider text-neutral-500">
            Средние и прогноз
          </p>
          <ul className="flex flex-col gap-1.5 text-sm">
            <li className="flex items-center justify-between rounded-lg border border-neutral-800 bg-neutral-950/40 px-3 py-2">
              <span className="text-neutral-400">Средний расход</span>
              <span className="text-neutral-200">
                {usd(initial.avg_day_7d)}/день (7д) · {usd(initial.avg_day_30d)}/день (30д)
              </span>
            </li>
            <li className="flex items-center justify-between rounded-lg border border-neutral-800 bg-neutral-950/40 px-3 py-2">
              <span className="text-neutral-400">Прогноз на 30 дней</span>
              <span className="text-neutral-200">{usd(forecast)}</span>
            </li>
            <li className="flex items-center justify-between rounded-lg border border-neutral-800 bg-neutral-950/40 px-3 py-2">
              <span className="text-neutral-400">Баланса хватит</span>
              <span
                className={
                  runway !== null && runway < 7 ? "text-amber-300" : "text-neutral-200"
                }
              >
                {runway !== null
                  ? `≈ ${runway} дн.`
                  : balance?.configured
                    ? "нет расхода — не тратится"
                    : "—"}
              </span>
            </li>
          </ul>
          {initial.by_task.length > 0 ? (
            <ul className="flex flex-col gap-1.5">
              {initial.by_task.map((item) => (
                <li
                  key={item.task}
                  className="flex items-center justify-between rounded-lg border border-neutral-800 bg-neutral-950/40 px-3 py-1.5 text-xs"
                >
                  <span className="text-neutral-400">
                    {AI_TASK_LABELS[item.task] ?? item.task}
                  </span>
                  <span className="text-neutral-300">
                    {item.runs} зап. · {usd(item.cost_usd)}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-neutral-500">
              Пока не было AI-запросов — расходы появятся после первого обхода с
              модерацией или дайджеста.
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
