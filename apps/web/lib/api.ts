"use client";
// Client για το App API (docs/CONTRACTS.md). Τα σχήματα εδώ καθρεφτίζουν τα contracts — αλλάζουν μαζί.
import { useCallback, useEffect, useState } from "react";

export const API_URL = process.env.NEXT_PUBLIC_APP_API_URL ?? "http://localhost:8000";

export type Urgency = "high" | "medium" | "low" | "none";

export interface Factor {
  name: string;
  impact_days: number | null;
  source: string;
}

export interface Evidence {
  model_version: string;
  burn_rate_per_day: number | null;
  burn_rate_recent_per_day: number | null;
  last_purchase_date: string | null;
  last_purchase_qty: number | null;
  avg_interval_days: number | null;
  purchases_count: number;
  est_stock_at_cutoff: number | null;
  seasonal_multiplier: number | null;
  promo: { name: string; disc_prc: number; from: string; to: string } | null;
  cold_start: boolean;
  peer_group: string | null;
  factors: Factor[];
  warnings: string[];
}

export interface SuggestionLine {
  MTRL: number;
  ITEM_CODE: string;
  ITEM_NAME: string;
  UNIT: string;
  QTY1: number;
  QTY_RECOMMENDED: number;
  QTY_MIN: number;
  QTY_MAX: number;
  PREDICTED_DEPLETION_DATE: string;
  CONFIDENCE: number;
  evidence: Evidence;
  PRICE?: number;        // € ανά UNIT (τιμή καταλόγου 2026) — από το API
  LINE_VALUE?: number;   // QTY1 × PRICE
}

export interface Suggestion {
  id: string;
  version: number;
  status: string;
  urgency: Exclude<Urgency, "none">;
  TRDR: number;
  CUSTOMER_CODE: string;
  CUSTOMER_NAME: string;
  CUSTOMER_CATEGORY: string;
  AREA: string;
  SALESMAN: number;
  SALESMAN_NAME: string;
  SUGGESTED_DELIVERY_DATE: string;
  REASON: string;
  LINES: SuggestionLine[];
  erp_draft_id: string | null;
  updated_at: string;
  VALUE?: number;        // € καθαρά, Σ LINE_VALUE
}

export interface Customer {
  TRDR: number;
  CODE: string;
  NAME: string;
  TRDCATEGORY: string;
  AREA: string;
  CITY: string;
  SALESMAN: number;
  SALESMAN_NAME: string | null;
  INSDATE: string;
  cold_start: boolean;
}

export interface Forecast {
  TRDR: number;
  MTRL: number;
  ITEM_NAME: string;
  CATEGORY: string;
  PREDICTED_DEPLETION_DATE: string | null;
  days_left: number | null;
  CONFIDENCE: number;
  urgency: Urgency;
}

export interface History {
  TRDR: number;
  items: { MTRL: number; ITEM_NAME: string; points: { date: string; qty: number }[] }[];
}

export interface Explanation {
  text: string;
  source: "llm" | "template";
  model: string | null;
}

export interface EvalRow {
  model: string;
  mae: number;
  within_3: number;
  within_7: number;
  at_risk_precision: number | null;
  at_risk_recall: number | null;
}

export interface Evaluation {
  source: string;
  cutoffs: string[];
  default_model: string;
  coverage: { pairs: number; targets: number; with_date: number; blank: number };
  readme_reference: Record<string, number>;
  truth?: string;
  mae_proxy?: Record<string, number>;
  rows: EvalRow[];
  per_cutoff: (EvalRow & { cutoff: string; n: number })[];
}

export async function apiGet<T>(path: string): Promise<T> {
  const r = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    throw new Error(body.message ?? `${r.status} ${r.statusText}`);
  }
  return r.json() as Promise<T>;
}

export const VOICE_URL = process.env.NEXT_PUBLIC_VOICE_URL ?? "http://localhost:8100";
/** Προαιρετικό: αν ο voice agent έχει VOICE_TRIGGER_TOKEN, το ίδιο εδώ. */
export const VOICE_TOKEN = process.env.NEXT_PUBLIC_VOICE_TOKEN ?? "";

export interface CallTurn { role: string; text: string; at: string }
export interface Call {
  call_sid: string;
  salesman: number | null;
  suggestion_ids: string[];
  status: string;
  started_at: string;
  ended_at: string | null;
  transcript: CallTurn[];
  erp_draft_ids: string[];
}

export interface Salesman { PRSN: number; NAME: string; phone: string | null }

export interface RiskRow extends Forecast {
  CUSTOMER_NAME: string;
  CUSTOMER_CATEGORY: string;
  AREA: string;
  SALESMAN: number;
  suggestion_id: string | null;
}

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) { super(message); }
}

export async function apiPost<T>(path: string, body: unknown = {}, base = API_URL, extraHeaders: Record<string, string> = {}): Promise<T> {
  const r = await fetch(`${base}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Actor": "dashboard", ...extraHeaders },
    body: JSON.stringify(body),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new ApiError(r.status, data.error ?? "error", data.message ?? data.detail?.[0]?.msg ?? `${r.status}`);
  return data as T;
}

/** Επαναφόρτωση ανά `ms` (π.χ. live κλήσεις). */
export function usePolling(reload: () => void, ms: number) {
  useEffect(() => {
    const id = setInterval(reload, ms);
    return () => clearInterval(id);
  }, [reload, ms]);
}

/** Φέρνει δεδομένα από το API. Στο refetch κρατά τα προηγούμενα δεδομένα (χωρίς flash). */
export function useApi<T>(path: string | null) {
  const [state, setState] = useState<{ key: string | null; data: T | null; error: string | null }>({
    key: null, data: null, error: null,
  });
  const [nonce, setNonce] = useState(0);
  const key = path ? `${path}#${nonce}` : null;

  useEffect(() => {
    if (!path || !key) return;
    let alive = true;
    apiGet<T>(path).then(
      (data) => alive && setState({ key, data, error: null }),
      (e: Error) => alive && setState((s) => ({ key, data: s.data, error: e.message })),
    );
    return () => { alive = false; };
  }, [path, key]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { data: state.data, error: state.error, loading: key !== null && state.key !== key, reload };
}
