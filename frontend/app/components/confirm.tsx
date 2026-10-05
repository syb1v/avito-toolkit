"use client";

import { createContext, useCallback, useContext, useMemo, useState } from "react";

import { Modal } from "@/app/components/modal";

type ConfirmOptions = {
  title: string;
  text?: string;
  confirmLabel?: string;
  danger?: boolean;
};

type ConfirmState = ConfirmOptions & { resolve: (value: boolean) => void };

const ConfirmContext = createContext<{
  confirm: (options: ConfirmOptions) => Promise<boolean>;
}>({ confirm: async () => false });

export function useConfirm() {
  return useContext(ConfirmContext).confirm;
}

export function ConfirmProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<ConfirmState | null>(null);

  const confirm = useCallback(
    (options: ConfirmOptions) =>
      new Promise<boolean>((resolve) => {
        setState({ ...options, resolve });
      }),
    [],
  );

  const close = useCallback(
    (value: boolean) => {
      setState((current) => {
        current?.resolve(value);
        return null;
      });
    },
    [],
  );

  const value = useMemo(() => ({ confirm }), [confirm]);

  return (
    <ConfirmContext.Provider value={value}>
      {children}
      <Modal
        open={state !== null}
        onClose={() => close(false)}
        title={state?.title ?? ""}
        maxWidth="max-w-md"
        footer={
          <>
            <button
              type="button"
              onClick={() => close(false)}
              className="rounded-lg border border-neutral-700 px-4 py-1.5 text-xs text-neutral-300 transition hover:border-neutral-500"
            >
              Отмена
            </button>
            <button
              type="button"
              onClick={() => close(true)}
              className={
                state?.danger
                  ? "rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-1.5 text-xs text-red-200 transition hover:bg-red-500/20"
                  : "rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-4 py-1.5 text-xs text-emerald-200 transition hover:bg-emerald-500/20"
              }
            >
              {state?.confirmLabel ?? "Подтвердить"}
            </button>
          </>
        }
      >
        {state?.text ? <p className="text-sm text-neutral-300">{state.text}</p> : null}
      </Modal>
    </ConfirmContext.Provider>
  );
}
