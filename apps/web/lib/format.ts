// Ελληνική μορφοποίηση (κόμμα για δεκαδικά, ημερομηνίες «6 Νοε»).
const num = new Intl.NumberFormat("el-GR", { maximumFractionDigits: 2 });
const num1 = new Intl.NumberFormat("el-GR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const eur = new Intl.NumberFormat("el-GR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });
const eur2 = new Intl.NumberFormat("el-GR", { style: "currency", currency: "EUR", minimumFractionDigits: 2, maximumFractionDigits: 2 });
const pct = new Intl.NumberFormat("el-GR", { style: "percent", maximumFractionDigits: 0 });
const day = new Intl.DateTimeFormat("el-GR", { day: "numeric", month: "short", timeZone: "UTC" });
const dayLong = new Intl.DateTimeFormat("el-GR", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });

export const fmtNum = (v: number | null | undefined) => (v == null ? "–" : num.format(v));
export const fmt1 = (v: number | null | undefined) => (v == null ? "–" : num1.format(v));
export const fmtEur = (v: number | null | undefined) => (v == null ? "–" : eur.format(v));
export const fmtEur2 = (v: number | null | undefined) => (v == null ? "–" : eur2.format(v));
export const fmtPct = (v: number | null | undefined) => (v == null ? "–" : pct.format(v));
export const fmtDay = (iso: string | null | undefined) => (iso ? day.format(new Date(iso + "T00:00:00Z")) : "–");
export const fmtDayLong = (iso: string | null | undefined) => (iso ? dayLong.format(new Date(iso + "T00:00:00Z")) : "–");

/** «Σήμερα» στο σενάριο του challenge (README: «Σήμερα είναι 1/11/2026»), cutoff = 31/10. */
export const CUTOFF = "2026-10-31";
export const TODAY = "2026-11-01";

export const MODEL_LABELS: Record<string, string> = {
  "cutoff+30": "Όλα = cutoff + 30",
  baseline_180: "Baseline 180 ημερών",
  seasonal_group: "Εποχικός δείκτης",
  seasonal_yoy: "Πέρσι × τάση",
  cadence: "Κύκλος αγορών",
  "hybrid_0.6": "Hybrid v1",
  "hybrid_0.7": "Hybrid v2",
  hybrid_v2: "Hybrid v2",
  hybrid_v3: "Hybrid v3",
};

export const FACTOR_LABELS: Record<string, string> = {
  seasonality: "Εποχικότητα",
  purchase_cycle: "Κύκλος αγορών",
  promo_stockpile: "Απόθεμα από προσφορά",
};
