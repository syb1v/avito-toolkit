import { AgentsPanel } from "@/app/components/agents-panel";

export default function AgentsPage() {
  return <main className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-8 sm:px-6 sm:py-12"><header><h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Агенты</h1><p className="mt-2 text-sm text-neutral-400">Плейбуки, отчёты и предложения субагентов.</p></header><AgentsPanel /></main>;
}
