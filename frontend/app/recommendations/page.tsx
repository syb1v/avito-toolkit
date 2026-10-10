import { RecommendationCard } from "@/app/components/recommendation-card";
import { fetchRecommendations } from "@/lib/api";

export default async function RecommendationsPage() {
  const items = await fetchRecommendations();
  return (
    <main className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-8 sm:px-6 sm:py-12">
      <header><p className="mb-2 text-xs uppercase tracking-[0.18em] text-sky-300/70">Рабочая очередь</p><h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Рекомендации</h1><p className="mt-2 max-w-2xl text-sm text-neutral-400">Каждое предложение проверяется отдельно. Здесь видны текущая цена, предложение, выборка рынка и точечное редактирование.</p></header>
      {items.length === 0 ? <section className="rounded-xl border border-dashed border-neutral-800 bg-neutral-900/40 p-8 text-sm text-neutral-500">Сейчас нет предложений. Запустите сопоставление своих объявлений или дождитесь отчёта агента.</section> : <section className="flex flex-col gap-3">{items.map((item) => <RecommendationCard key={item.sku} item={item} />)}</section>}
    </main>
  );
}
