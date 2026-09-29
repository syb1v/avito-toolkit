import Link from "next/link";

import { API_URL, fetchHealth, fetchSearches } from "@/lib/api";

export default async function Home() {
  const [health, searches] = await Promise.all([fetchHealth(), fetchSearches()]);

  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-10 px-6 py-16">
      <header className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-4">
          <p className="text-sm uppercase tracking-widest text-neutral-500">
            avito-toolkit
          </p>
          <span
            className={`rounded-full border px-3 py-1 text-xs ${
              health
                ? "border-emerald-500/30 bg-emerald-500/15 text-emerald-300"
                : "border-red-500/30 bg-red-500/10 text-red-300"
            }`}
          >
            {health ? `API ${health.version} · на связи` : "API недоступен"}
          </span>
        </div>
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
          Аналитика рынка Авито
        </h1>
        <p className="max-w-2xl text-neutral-400">
          Сбор конкурентной выдачи, статистика цен с IQR-фильтрацией, прокси-метрики
          спроса и подготовка к массовому управлению объявлениями.
        </p>
      </header>

      <section className="flex flex-col gap-4">
        <div className="flex items-baseline justify-between gap-4">
          <h2 className="text-lg font-medium">Поиски</h2>
          <span className="text-xs text-neutral-500">{searches.length} шт.</span>
        </div>

        {searches.length === 0 ? (
          <div className="rounded-xl border border-dashed border-neutral-800 p-8">
            <p className="text-sm text-neutral-300">Поисков пока нет.</p>
            <p className="mt-1 text-sm text-neutral-500">
              Создайте первый поиск через API — Swagger доступен по адресу{" "}
              <a className="text-emerald-400 underline" href={`${API_URL}/docs`}>
                {API_URL}/docs
              </a>{" "}
              (раздел <code>searches</code> → <code>POST /api/v1/searches</code>).
            </p>
            <pre className="mt-4 overflow-x-auto rounded-lg bg-neutral-900 p-4 text-xs text-neutral-400">
{`curl -X POST ${API_URL}/api/v1/searches \\
  -H 'Content-Type: application/json' \\
  -d '{"name":"iPhone 15","url":"https://www.avito.ru/moskva/telefony?q=iphone+15"}'`}
            </pre>
          </div>
        ) : (
          <ul className="grid gap-4 sm:grid-cols-2">
            {searches.map((search) => (
              <li key={search.id}>
                <Link
                  href={`/searches/${search.id}`}
                  className="block rounded-xl border border-neutral-800 bg-neutral-900/60 p-5 transition hover:border-neutral-600"
                >
                  <p className="font-medium">{search.name}</p>
                  <p className="mt-1 truncate text-xs text-neutral-500">{search.url}</p>
                  <div className="mt-4 flex flex-wrap gap-x-4 gap-y-1 text-xs text-neutral-500">
                    <span>cron: {search.schedule_cron}</span>
                    <span>приоритет: {search.priority}</span>
                    <span
                      className={search.is_active ? "text-emerald-400" : "text-neutral-500"}
                    >
                      {search.is_active ? "активен" : "на паузе"}
                    </span>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
