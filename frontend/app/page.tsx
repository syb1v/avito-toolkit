import { fetchHealth, API_URL } from "@/lib/api";

const ROADMAP = [
  { phase: "0", title: "Каркас, инфраструктура, CI", status: "done" },
  { phase: "1", title: "Коллектор Level 1 (curl_cffi), снапшоты цен", status: "next" },
  { phase: "2", title: "Аналитика (IQR, медианы) и дашборд", status: "planned" },
  { phase: "3", title: "Level 2 fallback (Patchright/Camoufox)", status: "planned" },
  { phase: "4", title: "Матчинг + AI-дайджесты и рекомендации", status: "planned" },
  { phase: "5", title: "Официальный API: сравнение своих цен", status: "planned" },
  { phase: "6", title: "Автозагрузка: массовый репрайсинг", status: "planned" },
];

const STATUS_STYLES: Record<string, string> = {
  done: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  next: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  planned: "bg-neutral-500/10 text-neutral-400 border-neutral-700",
};

const STATUS_LABELS: Record<string, string> = {
  done: "готово",
  next: "следующая",
  planned: "план",
};

export default async function Home() {
  const health = await fetchHealth();

  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-10 px-6 py-16">
      <header className="flex flex-col gap-3">
        <p className="text-sm uppercase tracking-widest text-neutral-500">
          avito-toolkit
        </p>
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
          Аналитика рынка Авито и управление объявлениями
        </h1>
        <p className="max-w-2xl text-neutral-400">
          Конкурентная разведка, статистика цен с IQR-фильтрацией, AI-рекомендации
          и массовый репрайсинг через официальный API.
        </p>
      </header>

      <section className="grid gap-4 sm:grid-cols-3">
        <div className="rounded-xl border border-neutral-800 bg-neutral-900/60 p-5">
          <p className="text-xs uppercase tracking-wider text-neutral-500">API</p>
          <p className="mt-2 text-lg font-medium">
            {health ? "на связи" : "недоступен"}
          </p>
          <p className="mt-1 text-sm text-neutral-500">{API_URL}</p>
        </div>
        <div className="rounded-xl border border-neutral-800 bg-neutral-900/60 p-5">
          <p className="text-xs uppercase tracking-wider text-neutral-500">
            Версия backend
          </p>
          <p className="mt-2 text-lg font-medium">{health?.version ?? "—"}</p>
          <p className="mt-1 text-sm text-neutral-500">
            окружение: {health?.environment ?? "—"}
          </p>
        </div>
        <div className="rounded-xl border border-neutral-800 bg-neutral-900/60 p-5">
          <p className="text-xs uppercase tracking-wider text-neutral-500">
            Дорожная карта
          </p>
          <p className="mt-2 text-lg font-medium">фаза 1</p>
          <p className="mt-1 text-sm text-neutral-500">коллектор выдачи</p>
        </div>
      </section>

      <section className="rounded-xl border border-neutral-800">
        <ul className="divide-y divide-neutral-800">
          {ROADMAP.map((item) => (
            <li
              key={item.phase}
              className="flex items-center justify-between gap-4 px-5 py-3"
            >
              <div className="flex items-center gap-4">
                <span className="w-6 text-sm tabular-nums text-neutral-500">
                  {item.phase}
                </span>
                <span className="text-sm text-neutral-200">{item.title}</span>
              </div>
              <span
                className={`rounded-full border px-2.5 py-0.5 text-xs ${STATUS_STYLES[item.status]}`}
              >
                {STATUS_LABELS[item.status]}
              </span>
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
