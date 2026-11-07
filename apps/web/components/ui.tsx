import Link from "next/link";
import type { ReactNode } from "react";
import { CALL_STATUS, SUGGESTION_STATUS, URGENCY } from "@/lib/format";
import type { CallStatus, SuggestionStatus, Urgency } from "@/lib/types";

export type Tone = "neutral" | "info" | "good" | "warning" | "critical";

const TONE: Record<Tone, string> = {
  neutral: "bg-surface-2 text-ink-2 ring-line",
  info: "bg-tint-info text-ink ring-line",
  good: "bg-tint-good text-good-ink ring-line",
  warning: "bg-tint-warning text-ink ring-line",
  critical: "bg-tint-critical text-critical ring-line",
};

const DOT: Record<Tone, string> = {
  neutral: "bg-muted",
  info: "bg-series",
  good: "bg-good",
  warning: "bg-warning",
  critical: "bg-critical",
};

export function Badge({ tone = "neutral", children, dot = true, title }: { tone?: Tone; children: ReactNode; dot?: boolean; title?: string }) {
  return (
    <span title={title} className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${TONE[tone]}`}>
      {dot && <span aria-hidden className={`size-1.5 rounded-full ${DOT[tone]}`} />}
      {children}
    </span>
  );
}

/** Επείγον: χρώμα + εικονίδιο + λέξη (ποτέ μόνο χρώμα). */
export function UrgencyBadge({ urgency }: { urgency: Urgency }) {
  const u = URGENCY[urgency];
  const ink = u.tone === "critical" ? "text-critical" : u.tone === "warning" ? "text-ink" : "text-ink-2";
  const icon = u.tone === "critical" ? "text-critical" : u.tone === "warning" ? "text-warning" : "text-muted";
  return (
    <span className={`inline-flex items-center gap-1 whitespace-nowrap text-xs font-semibold ${ink}`}>
      <span aria-hidden className={icon}>{u.icon}</span>
      {u.label}
    </span>
  );
}

export function SuggestionStatusBadge({ status }: { status: SuggestionStatus }) {
  const s = SUGGESTION_STATUS[status] ?? { label: status, tone: "neutral" as Tone };
  return <Badge tone={s.tone}>{s.label}</Badge>;
}

export function CallStatusBadge({ status }: { status: CallStatus }) {
  const s = CALL_STATUS[status] ?? { label: status, tone: "neutral" as Tone, live: false };
  return <Badge tone={s.tone}>{s.label}</Badge>;
}

export function Card({ children, className = "", title, action, id }: { children: ReactNode; className?: string; title?: ReactNode; action?: ReactNode; id?: string }) {
  return (
    <section id={id} className={`rounded-xl bg-surface ring-1 ring-line ${className}`}>
      {(title || action) && (
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-3">
          <h2 className="text-sm font-semibold text-ink">{title}</h2>
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

export function PageHeader({ title, subtitle, action }: { title: string; subtitle?: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-ink sm:text-2xl">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-ink-2">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export function Stat({ label, value, hint, href }: { label: string; value: ReactNode; hint?: ReactNode; href?: string }) {
  const body = (
    <>
      <div className="text-xs font-medium text-ink-2">{label}</div>
      <div className="mt-1 text-3xl font-semibold tracking-tight text-ink">{value}</div>
      {hint && <div className="mt-1 text-xs text-muted">{hint}</div>}
    </>
  );
  const cls = "block rounded-xl bg-surface p-4 ring-1 ring-line";
  return href ? (
    <Link href={href} className={`${cls} transition hover:ring-axis`}>{body}</Link>
  ) : (
    <div className={cls}>{body}</div>
  );
}

export function ErrorBox({ error, onRetry }: { error: { message: string }; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-tint-critical px-4 py-3 text-sm text-ink ring-1 ring-line">
      <span>
        <span aria-hidden className="mr-1.5 text-critical">✕</span>
        {error.message}
      </span>
      {onRetry && (
        <button onClick={onRetry} className="rounded-md px-2 py-1 text-xs font-medium ring-1 ring-line hover:bg-surface">
          Ξανά
        </button>
      )}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="px-4 py-10 text-center text-sm text-muted">{children}</div>;
}

export function Skeleton({ className = "h-24" }: { className?: string }) {
  return <div className={`animate-pulse rounded-xl bg-surface-2 ${className}`} />;
}

export function PageSkeleton() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-8 w-60" />
      <Skeleton className="h-28" />
      <Skeleton className="h-64" />
    </div>
  );
}

/** Λεπτή μπάρα βεβαιότητας (μία σειρά, ένα χρώμα) + ποσοστό σε κείμενο. */
export function ConfidenceBar({ value }: { value: number | null }) {
  if (value == null) return <span className="text-xs text-muted">—</span>;
  return (
    <span className="inline-flex items-center gap-2" title={`Βεβαιότητα μοντέλου ${Math.round(value * 100)}%`}>
      <span className="h-1.5 w-14 overflow-hidden rounded-full bg-surface-2">
        <span className="block h-full rounded-full bg-series" style={{ width: `${Math.round(value * 100)}%` }} />
      </span>
      <span className="tabular text-xs text-ink-2">{Math.round(value * 100)}%</span>
    </span>
  );
}

export const btn = {
  primary:
    "inline-flex items-center justify-center gap-2 rounded-lg bg-ink px-3.5 py-2 text-sm font-medium text-page transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40",
  secondary:
    "inline-flex items-center justify-center gap-2 rounded-lg bg-surface px-3.5 py-2 text-sm font-medium text-ink ring-1 ring-line transition hover:bg-surface-2 disabled:cursor-not-allowed disabled:opacity-40",
  ghost:
    "inline-flex items-center justify-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-ink-2 transition hover:bg-surface-2 hover:text-ink disabled:opacity-40",
};

export const input =
  "rounded-lg bg-surface px-3 py-2 text-sm text-ink ring-1 ring-line outline-none focus:ring-2 focus:ring-series";
