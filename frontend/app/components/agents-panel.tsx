"use client";

import { useEffect, useState } from "react";

import { useToast } from "@/app/components/toast";
import { InfoHint } from "@/app/components/info-hint";
import {
  createAgentPlaybookClient,
  deleteAgentPlaybookClient,
  fetchAgentPlaybooksClient,
  runAgentPlaybookClient,
  type AgentPlaybook,
  type AgentReportOut,
} from "@/lib/api";
import { formatRelativeTime } from "@/lib/format";

export function AgentsPanel() {
  const [playbooks, setPlaybooks] = useState<AgentPlaybook[]>([]);
  const [name, setName] = useState("");
  const [category, setCategory] = useState("");
  const [notes, setNotes] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [report, setReport] = useState<{ name: string; data: AgentReportOut } | null>(null);
  const toast = useToast();

  async function load() {
    setPlaybooks(await fetchAgentPlaybooksClient());
  }

  useEffect(() => {
    load();
  }, []);

  async function create() {
    if (!name.trim() || !category.trim()) {
      toast.push("error", "Укажите название и категорию");
      return;
    }
    const result = await createAgentPlaybookClient({
      name: name.trim(),
      category: category.trim(),
      criteria: notes.trim() ? { notes: notes.trim() } : {},
    });
    if (result.error) {
      toast.push("error", result.error);
      return;
    }
    setName("");
    setCategory("");
    setNotes("");
    toast.push("success", "Плейбук создан");
    await load();
  }

  async function run(playbook: AgentPlaybook) {
    setBusyId(playbook.id);
    const result = await runAgentPlaybookClient(playbook.id);
    setBusyId(null);
    if (result.error) {
      toast.push("error", result.error);
      return;
    }
    setReport({ name: playbook.name, data: result.report as AgentReportOut });
    await load();
  }

  return (
    <section className="rounded-xl border border-neutral-800 bg-neutral-900/60 p-4 sm:p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center">
          <h2 className="text-base font-medium sm:text-lg">Агенты по категориям</h2>
          <InfoHint
            title="Что это"
            text="Плейбук — ваши критерии по категории (целевые цены, конкуренты, что важно). Агент собирает рынок и ваши товары по категории и даёт отчёт простым языком. Ночью отчёты обновляются автоматически; задел под локальные модели — LLM_LOCAL_BASE_URL."
          />
        </div>
        <span className="text-xs text-neutral-500">{playbooks.length} плейбуков</span>
      </div>

      {playbooks.length > 0 ? (
        <ul className="mt-3 flex flex-col gap-2">
          {playbooks.map((playbook) => (
            <li
              key={playbook.id}
              className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-neutral-800 bg-neutral-950/40 px-3 py-2"
            >
              <div className="min-w-0">
                <p className="text-sm text-neutral-200">
                  {playbook.name}
                  <span className="ml-2 text-xs text-neutral-500">{playbook.category}</span>
                </p>
                {playbook.last_headline ? (
                  <p className="truncate text-xs text-neutral-500" title={playbook.last_headline}>
                    последний отчёт: {playbook.last_headline}
                  </p>
                ) : (
                  <p className="text-xs text-neutral-600">отчёт ещё не запускался</p>
                )}
              </div>
              <div className="flex gap-2">
                <button
                  type="button"
                  disabled={busyId === playbook.id}
                  onClick={() => run(playbook)}
                  className="rounded-lg border border-violet-500/40 bg-violet-500/10 px-3 py-1 text-xs text-violet-200 transition hover:bg-violet-500/20 disabled:opacity-50"
                >
                  {busyId === playbook.id ? "Анализ…" : "Запустить"}
                </button>
                <button
                  type="button"
                  onClick={async () => {
                    await deleteAgentPlaybookClient(playbook.id);
                    await load();
                  }}
                  className="rounded-lg border border-red-500/30 px-3 py-1 text-xs text-red-300 transition hover:border-red-500/60"
                >
                  Удалить
                </button>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-xs text-neutral-500">
          Пока нет плейбуков — добавьте первый, например «Devialet агент».
        </p>
      )}

      <div className="mt-4 grid gap-2 sm:grid-cols-[1fr_1fr_2fr_auto]">
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Название (Devialet агент)"
          className="rounded-lg border border-neutral-800 bg-neutral-950 px-3 py-1.5 text-sm text-neutral-200 outline-none focus:border-sky-500/60"
        />
        <input
          value={category}
          onChange={(event) => setCategory(event.target.value)}
          placeholder="Категория (Devialet)"
          className="rounded-lg border border-neutral-800 bg-neutral-950 px-3 py-1.5 text-sm text-neutral-200 outline-none focus:border-sky-500/60"
        />
        <input
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
          placeholder="Критерии: целевые цены, конкуренты, что важно"
          className="rounded-lg border border-neutral-800 bg-neutral-950 px-3 py-1.5 text-sm text-neutral-200 outline-none focus:border-sky-500/60"
        />
        <button
          type="button"
          onClick={create}
          className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-1.5 text-xs text-emerald-200 transition hover:bg-emerald-500/20"
        >
          Добавить плейбук
        </button>
      </div>

      {report ? (
        <div className="mt-4 rounded-lg border border-violet-500/25 bg-violet-500/5 p-3 text-sm text-neutral-200">
          <div className="flex items-center justify-between gap-2">
            <p className="font-medium">
              {report.name}: {report.data.headline}
            </p>
            <button
              type="button"
              onClick={() => setReport(null)}
              className="text-xs text-neutral-500 hover:text-neutral-300"
            >
              скрыть
            </button>
          </div>
          <p className="mt-1 text-neutral-300">{report.data.market_view}</p>
          {report.data.price_actions.length > 0 ? (
            <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-neutral-300">
              {report.data.price_actions.map((action) => (
                <li key={action.sku}>
                  <span className="font-mono text-neutral-500">{action.sku}</span> —{" "}
                  {action.suggestion}
                </li>
              ))}
            </ul>
          ) : null}
          {report.data.risks.length > 0 ? (
            <p className="mt-2 text-xs text-amber-300/80">
              Риски: {report.data.risks.join("; ")}
            </p>
          ) : null}
          <p className="mt-1 text-[11px] text-neutral-600">
            сохранён как артефакт · {formatRelativeTime(new Date().toISOString())}
          </p>
        </div>
      ) : null}
    </section>
  );
}
