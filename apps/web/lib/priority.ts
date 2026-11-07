import type { Suggestion } from "./api";
import { CUTOFF } from "./format";

/**
 * Προτεραιότητα για τον πωλητή — μόνο στο dashboard. Το `urgency` του contract (high/medium/low) δεν αλλάζει,
 * γιατί το χρησιμοποιεί και ο voice agent.
 *
 * Μέτρο: πόσους κύκλους έχει περάσει ο πελάτης χωρίς να αγοράσει = μέρες από την τελευταία αγορά / κύκλος αγορών
 * (το χειρότερο είδος της πρότασης). Κατανομή στα 105 «Επείγον» του v3: <1,5× ≈ 65, 1,5–3× ≈ 37, ≥3× = 3.
 */
export type Priority = "critical" | "high" | "lost" | "medium" | "low";

export const CRITICAL_RATIO = 1.5;   // έχει χάσει μισό κύκλο ή παραπάνω → μάλλον έχει ήδη ξεμείνει
export const LOST_RATIO = 3;         // τρεις κύκλοι χωρίς αγορά → δεν είναι θέμα αποθέματος, μάλλον τον χάσαμε

export const PRIORITY_ORDER: Record<Priority, number> = { critical: 0, high: 1, lost: 2, medium: 3, low: 4 };

export interface PriorityInfo {
  priority: Priority;
  ratio: number | null;        // κύκλοι χωρίς αγορά (χειρότερο είδος)
  daysSince: number | null;    // μέρες από την τελευταία αγορά αυτού του είδους
  interval: number | null;     // ο κύκλος του
  item: string | null;
}

const DAY = 86_400_000;
const cutoffMs = Date.parse(CUTOFF + "T00:00:00Z");

export function priorityOf(s: Suggestion): PriorityInfo {
  let worst: Omit<PriorityInfo, "priority"> = { ratio: null, daysSince: null, interval: null, item: null };
  for (const l of s.LINES) {
    const e = l.evidence;
    if (!e?.last_purchase_date || !e.avg_interval_days) continue;
    const since = Math.round((cutoffMs - Date.parse(e.last_purchase_date + "T00:00:00Z")) / DAY);
    const ratio = since / e.avg_interval_days;
    if (worst.ratio == null || ratio > worst.ratio) worst = { ratio, daysSince: since, interval: e.avg_interval_days, item: l.ITEM_NAME };
  }
  const r = worst.ratio ?? 0;
  const priority: Priority = r >= LOST_RATIO ? "lost" : s.urgency === "high" && r >= CRITICAL_RATIO ? "critical" : s.urgency;
  return { priority, ...worst };
}

/** Μία πρόταση σε μία φράση: γιατί είναι σε αυτό το επίπεδο. */
export function priorityReason(p: PriorityInfo): string | null {
  if (p.ratio == null || p.daysSince == null || p.interval == null) return null;
  const base = `${p.item}: ${p.daysSince} μέρες από την τελευταία αγορά, συνήθως κάθε ~${Math.round(p.interval)}`;
  if (p.priority === "lost") return `${base} — δεν αγοράζει τίποτα εδώ και καιρό· μάλλον θέλει τηλέφωνο, όχι παραγγελία.`;
  if (p.priority === "critical") return `${base} — έχει χάσει τον κύκλο του, πιθανότατα έχει ήδη ξεμείνει.`;
  return null;
}

/** Ταξινόμηση: επίπεδο → αξία (€) → πρώτη εξάντληση. */
export function byPriority(a: Suggestion, b: Suggestion): number {
  const pa = priorityOf(a), pb = priorityOf(b);
  return PRIORITY_ORDER[pa.priority] - PRIORITY_ORDER[pb.priority]
    || (b.VALUE ?? 0) - (a.VALUE ?? 0)
    || a.LINES[0].PREDICTED_DEPLETION_DATE.localeCompare(b.LINES[0].PREDICTED_DEPLETION_DATE);
}
