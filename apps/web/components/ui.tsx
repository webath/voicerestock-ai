import type { ReactNode } from "react";
import type { Urgency } from "@/lib/api";

export function PageHeader({ title, subtitle, children }: { title: string; subtitle?: ReactNode; children?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-ink-2">{subtitle}</p>}
      </div>
      {children}
    </div>
  );
}

export function Card({ title, subtitle, children, className = "" }: {
  title?: string; subtitle?: ReactNode; children: ReactNode; className?: string;
}) {
  return (
    <section className={`card min-w-0 p-5 ${className}`}>
      {title && <h2 className="text-base font-semibold text-ink">{title}</h2>}
      {subtitle && <p className="mt-0.5 text-sm text-ink-2">{subtitle}</p>}
      <div className={title || subtitle ? "mt-4" : ""}>{children}</div>
    </section>
  );
}

/** Stat tile: label · value · (προαιρετικά) σημείωση. */
export function StatTile({ label, value, note, hero = false }: { label: string; value: ReactNode; note?: ReactNode; hero?: boolean }) {
  return (
    <div className="card min-w-0 p-5">
      <div className="text-sm text-ink-2">{label}</div>
      <div className={`mt-1 font-semibold text-ink ${hero ? "text-5xl" : "text-3xl"}`}>{value}</div>
      {note && <div className="mt-1 text-xs text-ink-muted">{note}</div>}
    </div>
  );
}

const URGENCY: Record<Urgency, { label: string; color: string; icon: string }> = {
  high: { label: "Επείγον", color: "var(--critical)", icon: "●" },
  medium: { label: "Σύντομα", color: "var(--serious)", icon: "◐" },
  low: { label: "Χαμηλό", color: "var(--good)", icon: "○" },
  none: { label: "Καμία εξάντληση σε 90 μέρες", color: "var(--ink-muted)", icon: "–" },
};

/** Status = εικονίδιο + κείμενο, ποτέ μόνο χρώμα. */
export function UrgencyBadge({ urgency }: { urgency: Urgency }) {
  const u = URGENCY[urgency];
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border border-line px-2 py-0.5 text-xs text-ink-2">
      <span aria-hidden style={{ color: u.color }}>{u.icon}</span>
      {u.label}
    </span>
  );
}

export function Chip({ children, title }: { children: ReactNode; title?: string }) {
  return (
    <span title={title} className="inline-flex items-center whitespace-nowrap rounded-md bg-surface-2 px-2 py-0.5 text-xs text-ink-2">
      {children}
    </span>
  );
}

export function ErrorBox({ message }: { message: string }) {
  return (
    <div className="card p-4 text-sm text-ink-2" role="alert">
      <strong className="text-ink">Δεν φορτώθηκαν τα δεδομένα.</strong> {message}
      <div className="mt-1 text-ink-muted">
        Τρέχει το App API; <code>./scripts/dev_backend.sh</code> (ή <code>python3 scripts/mock_app_api.py</code>)
      </div>
    </div>
  );
}

export function Loading() {
  return <div className="py-10 text-center text-sm text-ink-muted">Φόρτωση…</div>;
}
