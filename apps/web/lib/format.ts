import type { CallStatus, SuggestionStatus, Urgency } from "./types";

/** «Σήμερα» του σεναρίου της Revival (README: «Σήμερα είναι 1/11/2026»). Ίδιο με το SCENARIO_TODAY του App API. */
export const SCENARIO_TODAY = process.env.NEXT_PUBLIC_SCENARIO_TODAY ?? "2026-11-01";

const DAY = 86_400_000;
const parse = (iso: string) => new Date(`${iso.slice(0, 10)}T00:00:00Z`);

export function daysBetween(fromIso: string, toIso: string): number {
  return Math.round((parse(toIso).getTime() - parse(fromIso).getTime()) / DAY);
}

export function addDays(iso: string, days: number): string {
  return new Date(parse(iso).getTime() + days * DAY).toISOString().slice(0, 10);
}

const dateFmt = new Intl.DateTimeFormat("el-GR", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });
const longFmt = new Intl.DateTimeFormat("el-GR", { weekday: "long", day: "numeric", month: "long", timeZone: "UTC" });
const timeFmt = new Intl.DateTimeFormat("el-GR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
const monthFmt = new Intl.DateTimeFormat("el-GR", { month: "short", timeZone: "UTC" });
const num = new Intl.NumberFormat("el-GR", { maximumFractionDigits: 1 });

/** 2026-11-03 → «Τρί 3 Νοε» */
export const fmtDate = (iso: string | null | undefined) => (iso ? dateFmt.format(parse(iso)) : "—");
/** 2026-11-03 → «Τρίτη 3 Νοεμβρίου» */
export const fmtDateLong = (iso: string | null | undefined) => (iso ? longFmt.format(parse(iso)) : "—");
export const fmtMonth = (d: Date) => monthFmt.format(d).replace(".", "");
export const fmtTime = (iso: string) => timeFmt.format(new Date(iso));
export const fmtNum = (n: number | null | undefined) => (n == null ? "—" : num.format(n));
export const fmtPct = (n: number | null | undefined) => (n == null ? "—" : `${Math.round(n * 100)}%`);

export function fmtDaysLeft(days: number | null | undefined): string {
  if (days == null) return "καμία εξάντληση σε 90 ημ.";
  if (days < 0) return `πριν από ${-days} ημ.`;
  if (days === 0) return "σήμερα";
  if (days === 1) return "αύριο";
  return `σε ${days} ημέρες`;
}

export const unitLabel = (unit: string, qty = 2) =>
  unit === "ΚΙΒ" ? (qty === 1 ? "κιβώτιο" : "κιβώτια") : unit === "ΤΕΜ" ? (qty === 1 ? "τεμάχιο" : "τεμάχια") : unit;

/** Η νομική μορφή δεν χρειάζεται στις λίστες: «Mini Market Οικονομικό Μ.Ε.Π.Ε.» → «Mini Market Οικονομικό». */
export const shortCustomer = (name: string) =>
  name.replace(/\s+(Α\.?Ε\.?|Μ\.?Ε\.?Π\.?Ε\.?|Ε\.?Π\.?Ε\.?|Ο\.?Ε\.?|Ε\.?Ε\.?|Ι\.?Κ\.?Ε\.?)\s*$/u, "").trim();

export const URGENCY: Record<Urgency, { label: string; tone: "critical" | "warning" | "neutral"; icon: string; rank: number }> = {
  high: { label: "Επείγον", tone: "critical", icon: "▲", rank: 0 },
  medium: { label: "Σύντομα", tone: "warning", icon: "◆", rank: 1 },
  low: { label: "Χαμηλό", tone: "neutral", icon: "●", rank: 2 },
  none: { label: "Καμία εξάντληση", tone: "neutral", icon: "○", rank: 3 },
};

export const SUGGESTION_STATUS: Record<SuggestionStatus, { label: string; tone: "neutral" | "info" | "good" | "warning" | "critical" }> = {
  proposed: { label: "Πρόταση", tone: "neutral" },
  modified: { label: "Τροποποιημένη", tone: "info" },
  confirmed: { label: "Επιβεβαιωμένη", tone: "info" },
  posting: { label: "Αποστολή στο ERP…", tone: "info" },
  draft_created: { label: "Draft στο ERP", tone: "good" },
  failed: { label: "Αποτυχία ERP", tone: "critical" },
  cancelled: { label: "Απορρίφθηκε", tone: "neutral" },
};

export const CALL_STATUS: Record<CallStatus, { label: string; tone: "neutral" | "info" | "good" | "warning" | "critical"; live: boolean }> = {
  queued: { label: "Σε αναμονή", tone: "neutral", live: true },
  dialing: { label: "Καλεί…", tone: "info", live: true },
  connected: { label: "Συνδέθηκε", tone: "info", live: true },
  greeted: { label: "Χαιρετισμός", tone: "info", live: true },
  discussing: { label: "Συζήτηση", tone: "info", live: true },
  confirming: { label: "Επιβεβαίωση", tone: "warning", live: true },
  posting_draft: { label: "Draft στο ERP…", tone: "warning", live: true },
  draft_created: { label: "Draft δημιουργήθηκε", tone: "good", live: true },
  failed: { label: "Δεν απάντησε / αποτυχία", tone: "critical", live: false },
  cancelled: { label: "Ακυρώθηκε", tone: "neutral", live: false },
  ended: { label: "Ολοκληρώθηκε", tone: "neutral", live: false },
};

/** Από πού έρχονται οι δείκτες: ποτέ «επίσημη βαθμολογία» — τα επίσημα νούμερα τα ξέρει μόνο η Revival. */
export function evaluationSource(source: string): { tone: "warning" | "info"; text: string } {
  if (/mock/i.test(source)) return { tone: "warning", text: "Δείγμα (mock) — όχι πραγματικά αποτελέσματα." };
  if (source === "local_backtest") return { tone: "info", text: "Τοπικό backtest σε ιστορικά cutoffs — όχι η επίσημη βαθμολογία της Revival." };
  return { tone: "info", text: source };
}

export const OPEN_STATUSES: SuggestionStatus[] = ["proposed", "modified", "confirmed", "failed"];
