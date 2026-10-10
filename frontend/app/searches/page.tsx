import { SearchManager } from "@/app/components/search-manager";
import { fetchAccounts, fetchSearches } from "@/lib/api";

export default async function SearchesPage() {
  const [searches, accounts] = await Promise.all([fetchSearches(), fetchAccounts()]);
  return (
    <main className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-8 sm:px-6 sm:py-12">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Поиски</h1>
        <p className="mt-2 max-w-2xl text-sm text-neutral-400">Поисковые задачи, расписания и состояние обходов.</p>
      </header>
      <SearchManager initial={searches} accounts={accounts} />
    </main>
  );
}
