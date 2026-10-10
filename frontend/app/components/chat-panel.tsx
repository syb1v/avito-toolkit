"use client";

import { useEffect, useRef, useState } from "react";

import { Modal } from "@/app/components/modal";
import { useToast } from "@/app/components/toast";
import {
  clearChatSessionClient,
  createChatSessionClient,
  deleteChatSessionClient,
  fetchChatMessagesClient,
  fetchChatSessionsClient,
  runChatActionClient,
  sendChatMessageClient,
  type ChatMessageOut,
  type ChatSession,
} from "@/lib/api";
import { formatRelativeTime } from "@/lib/format";

const QUICK_PROMPTS = [
  "Какая сейчас обстановка по системе?",
  "Что с ценами у Devialet?",
  "Какие правки ждут подтверждения?",
  "Где мы дороже рынка?",
];

export function ChatButton() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="rounded-lg border border-violet-500/40 bg-violet-500/10 px-2.5 py-1.5 text-xs text-violet-200 transition hover:bg-violet-500/20"
        title="AI-ассистент"
      >
        💬 Чат
      </button>
      {open ? <ChatModal onClose={() => setOpen(false)} /> : null}
    </>
  );
}

export function ChatPanel() {
  return <ChatModal onClose={() => undefined} />;
}

function ChatModal({ onClose }: { onClose: () => void }) {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessageOut[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<Record<string, unknown> | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const toast = useToast();

  async function loadSessions(): Promise<string | null> {
    const list = await fetchChatSessionsClient();
    setSessions(list);
    return list[0]?.id ?? null;
  }

  async function openSession(id: string) {
    setSessionId(id);
    const history = await fetchChatMessagesClient(id);
    setMessages(history.filter((message) => message.role !== "tool"));
    const last = [...history].reverse().find((message) => message.tool_payload?.pending_action);
    setPending(
      (last?.tool_payload?.pending_action as Record<string, unknown> | undefined) ?? null,
    );
  }

  useEffect(() => {
    let cancelled = false;
    loadSessions().then((firstId) => {
      if (!cancelled && firstId) {
        openSession(firstId);
      }
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  async function newSession() {
    const result = await createChatSessionClient();
    if (!result.ok) {
      toast.push("error", result.error);
      return;
    }
    setSessions((current) => [result.data, ...current]);
    setSessionId(result.data.id);
    setMessages([]);
    setPending(null);
  }

  async function send(prompt?: string) {
    const value = (prompt ?? text).trim();
    if (!value) {
      return;
    }
    let id = sessionId;
    if (!id) {
      const created = await createChatSessionClient();
      if (!created.ok) {
        toast.push("error", created.error);
        return;
      }
      id = created.data.id;
      setSessionId(id);
      setSessions((current) => [created.data, ...current]);
    }
    setText("");
    setMessages((current) => [
      ...current,
      {
        id: `local-${Date.now()}`,
        session_id: id,
        role: "user",
        content: value,
        tool_name: null,
        tool_payload: null,
        created_at: new Date().toISOString(),
      },
    ]);
    setBusy(true);
    const result = await sendChatMessageClient(id, value);
    setBusy(false);
    if (!result.ok) {
      toast.push("error", result.error);
      return;
    }
    setMessages((current) => [...current, result.data.message]);
    setPending(result.data.pending_action as Record<string, unknown> | null);
    loadSessions().then(() => undefined);
  }

  async function confirmAction() {
    if (!sessionId || !pending) {
      return;
    }
    setBusy(true);
    const result = await runChatActionClient({
      session_id: sessionId,
      action_type: String(pending.type),
      search: (pending.search as string | null) ?? null,
      sku: (pending.sku as string | null) ?? null,
      price: (pending.price as number | null) ?? null,
    });
    setBusy(false);
    setPending(null);
    if (!result.ok) {
      toast.push("error", result.error);
      return;
    }
    setMessages((current) => [...current, result.data]);
    toast.push("success", "Действие выполнено");
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="AI-ассистент"
      subtitle="Сводка по системе, поиски, цены и правки — простым языком"
      maxWidth="max-w-3xl"
      footer={
        <button
          type="button"
          onClick={onClose}
          className="rounded-lg border border-neutral-700 px-4 py-1.5 text-xs text-neutral-300 transition hover:border-neutral-500"
        >
          Закрыть
        </button>
      }
    >
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <select
            value={sessionId ?? ""}
            onChange={(event) => event.target.value && openSession(event.target.value)}
            className="max-w-[240px] rounded-lg border border-neutral-800 bg-neutral-950 px-2 py-1.5 text-xs text-neutral-200 outline-none focus:border-sky-500/60"
          >
            {sessions.length === 0 ? <option value="">— диалогов нет —</option> : null}
            {sessions.map((item) => (
              <option key={item.id} value={item.id}>
                {item.title} · {formatRelativeTime(item.updated_at)}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={newSession}
            className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-2.5 py-1 text-xs text-emerald-200 transition hover:bg-emerald-500/20"
          >
            Новый диалог
          </button>
          <button
            type="button"
            disabled={!sessionId || busy}
            onClick={async () => {
              if (sessionId) {
                await clearChatSessionClient(sessionId);
                setMessages([]);
                setPending(null);
                toast.push("success", "Контекст очищен");
              }
            }}
            className="rounded-lg border border-neutral-700 px-2.5 py-1 text-xs text-neutral-300 transition hover:border-neutral-500 disabled:opacity-50"
          >
            Очистить контекст
          </button>
          <button
            type="button"
            disabled={!sessionId || busy}
            onClick={async () => {
              if (sessionId) {
                await deleteChatSessionClient(sessionId);
                const firstId = await loadSessions();
                if (firstId) {
                  await openSession(firstId);
                } else {
                  setSessionId(null);
                  setMessages([]);
                }
              }
            }}
            className="rounded-lg border border-red-500/30 px-2.5 py-1 text-xs text-red-300 transition hover:border-red-500/60 disabled:opacity-50"
          >
            Удалить
          </button>
        </div>

        <div className="flex min-h-[280px] flex-col gap-2 overflow-y-auto rounded-xl border border-neutral-800 bg-neutral-950/40 p-3">
          {messages.length === 0 ? (
            <div className="flex flex-col gap-2">
              <p className="text-xs text-neutral-500">Спросите что-нибудь или начните с:</p>
              <div className="flex flex-wrap gap-2">
                {QUICK_PROMPTS.map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    onClick={() => send(prompt)}
                    className="rounded-full border border-neutral-800 px-3 py-1 text-xs text-neutral-300 transition hover:border-neutral-600"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((message) => (
              <div
                key={message.id}
                className={`max-w-[85%] rounded-xl px-3 py-2 text-sm ${
                  message.role === "user"
                    ? "self-end bg-sky-500/15 text-sky-50"
                    : "self-start border border-neutral-800 bg-neutral-900/70 text-neutral-200"
                }`}
              >
                {message.content}
              </div>
            ))
          )}
          {busy ? (
            <p className="self-start text-xs text-neutral-500">Ассистент думает…</p>
          ) : null}
          <div ref={bottomRef} />
        </div>

        {pending ? (
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
            <span>
              Предлагается действие: <b>{String(pending.label ?? pending.type)}</b>
              {pending.search ? ` · ${String(pending.search)}` : ""}
              {pending.sku ? ` · ${String(pending.sku)}` : ""}
              {pending.price ? ` · ${String(pending.price)} ₽` : ""}
            </span>
            <span className="flex gap-2">
              <button
                type="button"
                disabled={busy}
                onClick={confirmAction}
                className="rounded-lg border border-emerald-500/40 bg-emerald-500/15 px-3 py-1 text-emerald-100 transition hover:bg-emerald-500/25 disabled:opacity-50"
              >
                Подтвердить
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => setPending(null)}
                className="rounded-lg border border-neutral-700 px-3 py-1 text-neutral-300 transition hover:border-neutral-500 disabled:opacity-50"
              >
                Отмена
              </button>
            </span>
          </div>
        ) : null}

        <div className="flex gap-2">
          <input
            value={text}
            onChange={(event) => setText(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                send();
              }
            }}
            placeholder="Спросите про рынок, цены, алерты…"
            className="flex-1 rounded-lg border border-neutral-800 bg-neutral-950 px-3 py-2 text-sm text-neutral-200 outline-none focus:border-sky-500/60"
          />
          <button
            type="button"
            disabled={busy || !text.trim()}
            onClick={() => send()}
            className="rounded-lg border border-sky-500/40 bg-sky-500/10 px-4 py-2 text-sm text-sky-200 transition hover:bg-sky-500/20 disabled:opacity-50"
          >
            Отправить
          </button>
        </div>
      </div>
    </Modal>
  );
}
