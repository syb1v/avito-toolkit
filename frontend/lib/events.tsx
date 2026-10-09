"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";

import { API_URL } from "@/lib/api";

export type LiveEvent = {
  type: string;
  payload: Record<string, unknown>;
  ts: string;
};

type Handler = (event: LiveEvent) => void;

const EventContext = createContext<{
  subscribe: (handler: Handler) => () => void;
  connected: boolean;
}>({ subscribe: () => () => {}, connected: false });

function wsUrl(): string {
  const base =
    API_URL || (typeof window !== "undefined" ? window.location.origin : "http://localhost:8000");
  return `${base.replace(/^http/, "ws")}/api/v1/ws`;
}

export function EventProvider({ children }: { children: React.ReactNode }) {
  const listeners = useRef<Set<Handler>>(new Set());
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    let closed = false;
    let attempt = 0;
    let socket: WebSocket | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;

    const connect = () => {
      socket = new WebSocket(wsUrl());
      socket.onopen = () => {
        attempt = 0;
        setConnected(true);
      };
      socket.onmessage = (message) => {
        try {
          const event = JSON.parse(message.data as string) as LiveEvent;
          if (event.type === "hello") {
            return;
          }
          for (const handler of listeners.current) {
            handler(event);
          }
        } catch {
          // мусор в канале игнорируем
        }
      };
      socket.onclose = () => {
        setConnected(false);
        if (!closed) {
          attempt += 1;
          retryTimer = setTimeout(connect, Math.min(15000, 1000 * 2 ** attempt));
        }
      };
      socket.onerror = () => {
        socket?.close();
      };
    };

    connect();
    const ping = setInterval(() => {
      if (socket?.readyState === WebSocket.OPEN) {
        socket.send("ping");
      }
    }, 25000);
    return () => {
      closed = true;
      clearInterval(ping);
      if (retryTimer) {
        clearTimeout(retryTimer);
      }
      socket?.close();
    };
  }, []);

  const subscribe = useCallback((handler: Handler) => {
    listeners.current.add(handler);
    return () => {
      listeners.current.delete(handler);
    };
  }, []);

  return (
    <EventContext.Provider value={{ subscribe, connected }}>{children}</EventContext.Provider>
  );
}

export function useEvents(
  handler: Handler,
  filter?: (event: LiveEvent) => boolean,
): void {
  const { subscribe } = useContext(EventContext);
  const handlerRef = useRef(handler);
  const filterRef = useRef(filter);
  handlerRef.current = handler;
  filterRef.current = filter;

  useEffect(
    () =>
      subscribe((event) => {
        if (filterRef.current && !filterRef.current(event)) {
          return;
        }
        handlerRef.current(event);
      }),
    [subscribe],
  );
}

export function useLiveConnected(): boolean {
  return useContext(EventContext).connected;
}
