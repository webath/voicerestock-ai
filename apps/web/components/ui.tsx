import type { ReactNode } from "react";
import type { Urgency } from "@/lib/api";

export function PageHeader({ title, subtitle, eyebrow, children }: {
  title: string; subtitle?: ReactNode; eyebrow?: ReactNode; children?: ReactNode;
}) {
  return (
    <div className="fade-in mb-7 flex flex-wrap items-end justify-between gap-4">
      <div>
        {eyebrow && <div className="mb-1 text-xs font-medium uppercase tracking-[0.14em] text-ink-muted">{eyebrow}</div>}
        <h1 className="text-[28px] font-semibold leading-tight tracking-tight text-ink">{title}</h1>
        {subtitle && <p className="mt-1.5 max-w-2xl text-sm text-ink-2">{subtitle}</p>}
      </div>
      {children}
    </div>
  );
}

export function Card({ title, subtitle, action, children, className = "", lift = false }: {
  title?: ReactNode; subtitle?: ReactNode; action?: ReactNode; children: ReactNode; className?: string; lift?: boolean;
}) {
  return (
    <section className={`card min-w-0 p-5 ${lift ? "lift" : ""} ${className}`}>
      {(title || action) && (
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            {title && <h2 className="text-base font-semibold text-ink">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-sm text-ink-2">{subtitle}</p>}
          </div>
          {action}
        </div>
      )}
      {!title && subtitle && <p className="text-sm text-ink-2">{subtitle}</p>}
      <div className={title || subtitle || action ? "mt-4" : ""}>{children}</div>
    </section>
  );
}

/** Stat tile: label · value · (προαιρετικά) σημείωση. */
export function StatTile({ label, value, note, hero = false }: { label: string; value: ReactNode; note?: ReactNode; hero?: boolean }) {
  return (
    <div className="card lift min-w-0 p-5">
      <div className="text-sm text-ink-2">{label}</div>
      <div className={`mt-1 font-semibold tracking-tight text-ink ${hero ? "text-5xl" : "text-3xl"}`}>{value}</div>
      {note && <div className="mt-1.5 text-xs text-ink-muted">{note}</div>}
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
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border border-line bg-surface-2 px-2 py-0.5 text-xs text-ink-2">
      <span aria-hidden style={{ color: u.color }}>{u.icon}</span>
      {u.label}
    </span>
  );
}

const STATUS: Record<string, { label: string; color: string; icon: string }> = {
  proposed: { label: "Προς έγκριση", color: "var(--ink-muted)", icon: "○" },
  modified: { label: "Τροποποιημένη", color: "var(--series-1)", icon: "◐" },
  confirmed: { label: "Επιβεβαιωμένη", color: "var(--series-1)", icon: "◑" },
  posting: { label: "Αποστολή…", color: "var(--warning)", icon: "◌" },
  draft_created: { label: "Draft στο ERP", color: "var(--good)", icon: "✓" },
  failed: { label: "Αποτυχία ERP", color: "var(--critical)", icon: "!" },
  cancelled: { label: "Ακυρώθηκε", color: "var(--ink-muted)", icon: "×" },
};

export function StatusBadge({ status }: { status: string }) {
  const s = STATUS[status] ?? { label: status, color: "var(--ink-muted)", icon: "•" };
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border border-line bg-surface-2 px-2 py-0.5 text-xs text-ink-2">
      <span aria-hidden style={{ color: s.color }} className="font-semibold">{s.icon}</span>
      {s.label}
    </span>
  );
}

export function Chip({ children, title }: { children: ReactNode; title?: string }) {
  return (
    <span title={title} className="inline-flex items-center whitespace-nowrap rounded-lg border border-line bg-surface-2 px-2 py-0.5 text-xs text-ink-2">
      {children}
    </span>
  );
}

/** Λεπτή μπάρα 0..1 (π.χ. confidence) — μονόχρωμη, με το ποσοστό δίπλα σε text ink. */
export function Meter({ value, label }: { value: number; label?: string }) {
  return (
    <span className="inline-flex items-center gap-2" title={label}>
      <span className="relative inline-block h-1.5 w-14 overflow-hidden rounded-full" style={{ background: "var(--series-1-wash)" }}>
        <span className="grow-x absolute inset-y-0 left-0 rounded-full" style={{ width: `${Math.round(value * 100)}%`, background: "var(--series-1)" }} />
      </span>
      <span className="tnum text-xs text-ink-2">{Math.round(value * 100)}%</span>
    </span>
  );
}

export function Segmented<T extends string>({ value, onChange, options, label }: {
  value: T; onChange: (v: T) => void; options: { value: T; label: string }[]; label: string;
}) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={o.value} type="button" aria-pressed={value === o.value} onClick={() => onChange(o.value)}>{o.label}</button>
      ))}
    </div>
  );
}

export function Select({ value, onChange, options, label }: {
  value: string; onChange: (v: string) => void; options: { value: string; label: string }[]; label: string;
}) {
  return (
    <select className="field pr-8" value={value} onChange={(e) => onChange(e.target.value)} aria-label={label}>
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
}

export function FilterBar({ children }: { children: ReactNode }) {
  return <div className="fade-in mb-5 flex flex-wrap items-center gap-2">{children}</div>;
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="card p-8 text-center">
      <div className="text-base font-semibold text-ink">{title}</div>
      {children && <div className="mx-auto mt-1.5 max-w-md text-sm text-ink-2">{children}</div>}
    </div>
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
  return (
    <div className="flex items-center justify-center gap-2 py-16 text-sm text-ink-muted" role="status">
      <span className="pulse-dot inline-block h-2 w-2 rounded-full" style={{ background: "var(--series-1)" }} />
      Φόρτωση…
    </div>
  );
}
