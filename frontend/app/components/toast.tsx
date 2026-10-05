"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
} from "react";

export type ToastKind = "success" | "error" | "info";

type ToastItem = { id: number; kind: ToastKind; text: string };

const ToastContext = createContext<{ push: (kind: ToastKind, text: string) => void }>({
  push: () => undefined,
});

export function useToast() {
  return useContext(ToastContext);
}

const TOAST_STYLES: Record<ToastKind, string> = {
  success: "border-emerald-500/40 bg-emerald-950/90 text-emerald-100",
  error: "border-red-500/40 bg-red-950/90 text-red-100",
  info: "border-sky-500/40 bg-sky-950/90 text-sky-100",
};

const TOAST_ICONS: Record<ToastKind, string> = {
  success: "✓",
  error: "!",
  info: "i",
};

const TOAST_TITLES: Record<ToastKind, string> = {
  success: "Готово",
  error: "Ошибка",
  info: "Информация",
};

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => {
    setItems((current) => current.filter((item) => item.id !== id));
  }, []);

  const push = useCallback(
    (kind: ToastKind, text: string) => {
      const id = nextId.current;
      nextId.current += 1;
      setItems((current) => [...current.slice(-3), { id, kind, text }]);
      setTimeout(() => dismiss(id), 4500);
    },
    [dismiss],
  );

  const value = useMemo(() => ({ push }), [push]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-[min(92vw,380px)] flex-col gap-2">
        {items.map((item) => (
          <div
            key={item.id}
            className={`toast-in pointer-events-auto flex items-start gap-3 rounded-xl border px-3.5 py-3 text-sm shadow-xl shadow-black/50 backdrop-blur ${TOAST_STYLES[item.kind]}`}
            role="status"
          >
            <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-current/30 text-[11px]">
              {TOAST_ICONS[item.kind]}
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-[11px] uppercase tracking-wide opacity-60">
                {TOAST_TITLES[item.kind]}
              </p>
              <p className="mt-0.5 break-words">{item.text}</p>
            </div>
            <button
              type="button"
              onClick={() => dismiss(item.id)}
              className="opacity-50 transition hover:opacity-100"
              title="Скрыть"
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
