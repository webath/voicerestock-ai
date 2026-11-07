"use client";

import { useCallback, useEffect, useState } from "react";

/** Σφάλμα του App API ({"error": "code", "message": "..."}) ή του voice agent. */
export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

async function request<T>(base: string, path: string, init?: RequestInit & { json?: unknown }): Promise<T> {
  const { json, ...rest } = init ?? {};
  let res: Response;
  try {
    res = await fetch(base + path, {
      ...rest,
      cache: "no-store",
      headers: { "Content-Type": "application/json", "X-Actor": "web:dashboard", ...(rest.headers ?? {}) },
      body: json === undefined ? rest.body : JSON.stringify(json),
    });
  } catch {
    throw new ApiError(0, "unreachable", "Δεν υπάρχει σύνδεση με τον server.");
  }
  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    /* όχι JSON (π.χ. 502 από το proxy) */
  }
  if (!res.ok) {
    const d = (data ?? {}) as { error?: string; message?: string };
    const fallback = res.status >= 500 ? "Ο server δεν απαντά." : `Σφάλμα ${res.status}`;
    throw new ApiError(res.status, d.error ?? "http_error", d.message ?? fallback);
  }
  return data as T;
}

/** App API (docs/CONTRACTS.md) — μέσω του proxy /backend → APP_API_URL/api */
export const api = <T,>(path: string, init?: RequestInit & { json?: unknown }) => request<T>("/backend", path, init);
/** Voice agent — μέσω του proxy /voice-api → VOICE_URL/voice */
export const voice = <T,>(path: string, init?: RequestInit & { json?: unknown }) => request<T>("/voice-api", path, init);

export interface ApiState<T> {
  data: T | undefined;
  error: ApiError | undefined;
  loading: boolean;
  reload: () => void;
}

/**
 * GET με προαιρετικό polling. Κρατά τα προηγούμενα δεδομένα όσο φορτώνει,
 * ώστε η σελίδα να μην «αναβοσβήνει» σε κάθε ανανέωση.
 */
export function useApi<T>(path: string | null, opts: { refreshMs?: number; client?: typeof api } = {}): ApiState<T> {
  const { refreshMs, client = api } = opts;
  const [state, setState] = useState<{ key: string | null; data?: T; error?: ApiError }>({ key: null });
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!path) return;
    let alive = true;
    const run = async () => {
      try {
        const data = await client<T>(path);
        if (alive) setState({ key: path, data });
      } catch (e) {
        const error = e instanceof ApiError ? e : new ApiError(0, "unknown", String(e));
        if (alive) setState((s) => ({ ...s, key: path, error }));
      }
    };
    void run();
    const t = refreshMs
      ? setInterval(() => {
          if (document.visibilityState === "visible") void run();
        }, refreshMs)
      : undefined;
    return () => {
      alive = false;
      if (t) clearInterval(t);
    };
  }, [path, refreshMs, client, tick]);

  const reload = useCallback(() => setTick((n) => n + 1), []);
  return {
    data: state.data,
    error: state.key === path ? state.error : undefined,
    loading: path != null && state.key !== path,
    reload,
  };
}
