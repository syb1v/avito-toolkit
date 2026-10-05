import { EditsPanel } from "@/app/components/edits-panel";
import { fetchEdits } from "@/lib/api";

export default async function EditsPage() {
  const initial = await fetchEdits();
  return (
    <main className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-8 sm:gap-8 sm:px-6 sm:py-12">
      <header className="flex flex-col gap-2">
        <h1 className="text-xl font-semibold tracking-tight sm:text-2xl">
          Правки объявлений
        </h1>
        <p className="max-w-3xl text-sm text-neutral-400">
          Управление ценами ваших объявлений: система предлагает целевую цену по рынку,
          вы одобряете изменения, и они применяются в кабинете продавца через браузер —
          с журналом «до/после», скриншотами и откатом. Официальный API Авито для этого
          не используется.
        </p>
      </header>
      <EditsPanel initial={initial} />
    </main>
  );
}
