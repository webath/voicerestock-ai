// Καταστάσεις κλήσης (docs/VOICE.md · state machine). Πάντα εικονίδιο + κείμενο.
export const CALL_STEPS = [
  { key: "dialing", label: "Κλήση" },
  { key: "connected", label: "Συνδέθηκε" },
  { key: "discussing", label: "Συζήτηση" },
  { key: "confirming", label: "Επιβεβαίωση" },
  { key: "posting_draft", label: "ERP" },
  { key: "draft_created", label: "Draft" },
] as const;

const ORDER: Record<string, number> = {
  queued: -1, dialing: 0, connected: 1, greeted: 1, discussing: 2, quantity_modified: 2,
  confirming: 3, explicit_confirmation: 3, validated: 3, posting_draft: 4, draft_created: 5,
};

const LABEL: Record<string, { label: string; color: string; icon: string }> = {
  queued: { label: "Σε αναμονή", color: "var(--ink-muted)", icon: "○" },
  dialing: { label: "Καλεί…", color: "var(--series-1)", icon: "◌" },
  connected: { label: "Σε γραμμή", color: "var(--series-1)", icon: "●" },
  greeted: { label: "Σε γραμμή", color: "var(--series-1)", icon: "●" },
  discussing: { label: "Συζήτηση", color: "var(--series-1)", icon: "●" },
  quantity_modified: { label: "Αλλαγή ποσότητας", color: "var(--series-1)", icon: "●" },
  confirming: { label: "Επιβεβαίωση", color: "var(--warning)", icon: "◑" },
  explicit_confirmation: { label: "Επιβεβαίωση", color: "var(--warning)", icon: "◑" },
  validated: { label: "Επιβεβαιώθηκε", color: "var(--warning)", icon: "◑" },
  posting_draft: { label: "Αποστολή στο ERP", color: "var(--warning)", icon: "◌" },
  draft_created: { label: "Draft στο ERP", color: "var(--good)", icon: "✓" },
  ended: { label: "Ολοκληρώθηκε", color: "var(--ink-muted)", icon: "■" },
  failed: { label: "Απέτυχε", color: "var(--critical)", icon: "!" },
  cancelled: { label: "Ακυρώθηκε", color: "var(--ink-muted)", icon: "×" },
};

export const isLive = (status: string) => !["ended", "failed", "cancelled", "draft_created"].includes(status);
export const stepIndex = (status: string) => ORDER[status] ?? -1;

export function CallStatusBadge({ status }: { status: string }) {
  const s = LABEL[status] ?? { label: status, color: "var(--ink-muted)", icon: "•" };
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border border-line bg-surface-2 px-2 py-0.5 text-xs text-ink-2">
      <span aria-hidden style={{ color: s.color }} className={isLive(status) && status !== "queued" ? "pulse-dot" : ""}>{s.icon}</span>
      {s.label}
    </span>
  );
}
