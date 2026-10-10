import { ProxyPanel } from "@/app/components/proxy-panel";

export default function ProxiesPage() {
  return <main className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-8 sm:px-6 sm:py-12"><header><h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Прокси</h1><p className="mt-2 text-sm text-neutral-400">Проверка доступности и лимитов прокси.</p></header><ProxyPanel /></main>;
}
