import { AutoRepricePanel } from "@/app/components/auto-reprice-panel";
import { OurListingsView } from "@/app/components/our-listings-view";
import { fetchOurListingsOverview, fetchRecommendations } from "@/lib/api";

export default async function OurListingsPage({
  searchParams,
}: {
  searchParams: Promise<{ sku?: string; seller?: string }>;
}) {
  const [{ sku, seller }, rows, recommendations] = await Promise.all([
    searchParams,
    searchParams.then(({ seller: selected }) => fetchOurListingsOverview(selected)),
    searchParams.then(({ seller: selected }) => fetchRecommendations(selected)),
  ]);

  return (
    <main className="mx-auto flex max-w-6xl flex-col gap-8 px-4 py-8 sm:px-6 sm:py-12">
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
          Наши объявления
        </h1>
        <p className="max-w-2xl text-sm text-neutral-400">
          Цены, матчи с рынком, рекомендации и авто-правки. Источники — импорт xlsx,
          API-аккаунты и ручное добавление. Клик по SKU — рынок, конкуренты и
          AI-обоснование.
        </p>
      </header>

      <AutoRepricePanel />

      {rows.length === 0 ? (
        <div className="rounded-xl border border-dashed border-neutral-800 p-6 text-sm text-neutral-400 sm:p-8">
          <p className="text-neutral-200">Пока пусто. Загрузите товары:</p>
          <p className="mt-3 text-xs text-neutral-500">
            «Поиски» → «Импорт из файла» (xlsx-выгрузка Авито) или «Аккаунты» →
            «Синхронизировать (API)» для API-аккаунта.
          </p>
        </div>
      ) : (
        <OurListingsView
          rows={rows}
          recommendations={recommendations}
          initialSku={sku ?? null}
        />
      )}
    </main>
  );
}
