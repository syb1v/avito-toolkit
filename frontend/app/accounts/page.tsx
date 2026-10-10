import { AccountManager } from "@/app/components/account-manager";
import { fetchAccounts } from "@/lib/api";

export default async function AccountsPage() {
  return <main className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-8 sm:px-6 sm:py-12"><header><h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Аккаунты</h1><p className="mt-2 text-sm text-neutral-400">Продавцы, поисковые аккаунты и их состояние.</p></header><AccountManager initial={await fetchAccounts()} /></main>;
}
