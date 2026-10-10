import { ChatPanel } from "@/app/components/chat-panel";

export default function ChatPage() {
  return <main className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-8 sm:px-6 sm:py-12"><header><h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Чат</h1><p className="mt-2 text-sm text-neutral-400">Вопросы, исследования и действия с обязательным подтверждением.</p></header><ChatPanel /></main>;
}
