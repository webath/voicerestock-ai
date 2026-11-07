// Σχήματα του App API — docs/CONTRACTS.md (η μόνη πηγή αλήθειας για τα πεδία).

/** «none» = καμία εξάντληση μέσα στις 90 μέρες (μόνο στο /api/forecasts). */
export type Urgency = "high" | "medium" | "low" | "none";
export type SuggestionStatus =
  | "proposed" | "modified" | "confirmed" | "posting" | "draft_created" | "failed" | "cancelled";

export interface Promo { name: string; disc_prc?: number; from: string; to: string }

export interface Evidence {
  model_version?: string;
  burn_rate_per_day?: number | null;
  last_purchase_date?: string | null;
  last_purchase_qty?: number | null;
  avg_interval_days?: number | null;
  purchases_count?: number | null;
  est_stock_at_cutoff?: number | null;
  seasonal_multiplier?: number | null;
  promo?: Promo | null;
  cold_start?: boolean;
  peer_group?: string | null;
  factors?: { name: string; impact_days?: number | null; source?: string }[];
  warnings?: string[];
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
  PREDICTED_DEPLETION_DATE: string | null;
  CONFIDENCE: number | null;
  evidence: Evidence;
}

export interface Suggestion {
  id: string;
  version: number;
  status: SuggestionStatus;
  urgency: Urgency;
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
}

export interface RiskRow {
  TRDR: number;
  CUSTOMER_NAME: string;
  CUSTOMER_CATEGORY?: string;
  AREA?: string;
  SALESMAN?: number;
  MTRL: number;
  ITEM_NAME: string;
  CATEGORY?: string;
  PREDICTED_DEPLETION_DATE: string | null;
  days_left: number | null;
  CONFIDENCE: number | null;
  urgency: Urgency;
  suggestion_id?: string;
}

export interface Salesman { PRSN: number; NAME: string; phone: string | null }

export interface Forecast {
  TRDR: number;
  MTRL: number;
  ITEM_NAME: string;
  CATEGORY?: string;
  PREDICTED_DEPLETION_DATE: string | null;
  days_left?: number | null;
  CONFIDENCE: number | null;
  urgency: Urgency;
}

export interface HistoryPoint { date: string; qty: number }
export interface History { TRDR: number; items: { MTRL: number; ITEM_NAME: string; points: HistoryPoint[] }[] }

export interface Explanation { text: string; source?: "llm" | "template"; model?: string | null; grounded_on: string[] }

export interface EvaluationRow {
  model: string;
  mae: number | null;
  within_3: number | null;
  within_7: number | null;
  at_risk_precision: number | null;
  at_risk_recall: number | null;
}
export interface Evaluation { source: string; cutoffs: string[]; rows: EvaluationRow[] }

export type CallStatus =
  | "queued" | "dialing" | "connected" | "greeted" | "discussing" | "confirming"
  | "posting_draft" | "draft_created" | "failed" | "cancelled" | "ended";

export interface Call {
  call_sid: string;
  salesman: number | null;
  suggestion_ids: string[];
  status: CallStatus;
  started_at: string;
  ended_at: string | null;
  transcript: { role: "agent" | "user"; text: string; at: string }[];
  erp_draft_ids: string[];
}

export interface VoiceHealth {
  ok: boolean;
  active_calls: string[];
  quiet_hours: boolean;
  salesmen_with_phone: number[];
}
