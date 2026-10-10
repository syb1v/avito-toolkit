import { AgentsPanel } from "@/app/components/agents-panel";
import { AgentRunView } from "@/app/components/agent-run-view";
import { fetchAgentPlaybooksClient, fetchDecisionsClient } from "@/lib/api";

export default async function AgentsPage() {
  const [playbooks, decisions] = await Promise.all([fetchAgentPlaybooksClient(), fetchDecisionsClient()]);
  return <main className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-8 sm:px-6 sm:py-12"><header><p className="mb-2 text-xs uppercase tracking-[0.18em] text-sky-300/70">Контроль AI</p><h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Агенты</h1><p className="mt-2 max-w-2xl text-sm text-neutral-400">Здесь видно, какие правила и данные использованы, что предложили субагенты и где требуется твоё решение.</p></header><AgentRunView playbooks={playbooks} decisions={decisions} /><AgentsPanel /></main>;
}
