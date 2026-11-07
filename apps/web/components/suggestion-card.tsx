"use client";

import Link from "next/link";
import { useState } from "react";
import { ApiError, api } from "@/lib/api";
import { OPEN_STATUSES, fmtDate, fmtDateLong, fmtNum, shortCustomer, unitLabel } from "@/lib/format";
import type { Explanation, Suggestion, SuggestionLine } from "@/lib/types";
import { Badge, ConfidenceBar, ErrorBox, SuggestionStatusBadge, UrgencyBadge, btn } from "./ui";

/** Chips ΜΟΝΟ όταν τα δίνει το evidence — ποτέ «διακοσμητικά». */
function EvidenceChips({ line }: { line: SuggestionLine }) {
  const e = line.evidence ?? {};
  const chips: { key: string; tone: "info" | "warning" | "neutral"; text: string; title?: string }[] = [];
  if (typeof e.seasonal_multiplier === "number") {
    const down = e.seasonal_multiplier < 1;
    chips.push({
      key: "season",
      tone: "neutral",
      text: `Εποχικότητα ${down ? "↓" : "↑"} ×${fmtNum(e.seasonal_multiplier)}`,
      title: "Εποχικός συντελεστής κατανάλωσης από το μοντέλο",
    });
  }
  if (e.promo) chips.push({ key: "promo", tone: "info", text: `Προσφορά${e.promo.disc_prc ? ` −${e.promo.disc_prc}%` : ""} · ${fmtDate(e.promo.from)}–${fmtDate(e.promo.to)}`, title: e.promo.name });
  if (e.cold_start) chips.push({ key: "cold", tone: "warning", text: `Νέος πελάτης${e.peer_group ? ` · σαν ${e.peer_group}` : ""}`, title: "Cold start: πρόβλεψη από παρόμοιους πελάτες" });
  for (const w of e.warnings ?? []) chips.push({ key: `w-${w}`, tone: "warning", text: w });
  if (!chips.length) return null;
  return (
    <div className="mt-1.5 flex flex-wrap gap-1.5">
      {chips.map((c) => (
        <Badge key={c.key} tone={c.tone} title={c.title}>{c.text}</Badge>
      ))}
    </div>
  );
}

function QtyStepper({ line, disabled, onSet }: { line: SuggestionLine; disabled: boolean; onSet: (q: number) => void }) {
  const changed = line.QTY1 !== line.QTY_RECOMMENDED;
  return (
    <div className="flex flex-col items-end gap-1">
      <div className="inline-flex items-center rounded-lg ring-1 ring-line">
        <button
          className="grid size-8 place-items-center rounded-l-lg text-ink-2 hover:bg-surface-2 disabled:opacity-30"
          disabled={disabled || line.QTY1 <= line.QTY_MIN}
          onClick={() => onSet(line.QTY1 - 1)}
          aria-label={`Μείωση ποσότητας ${line.ITEM_NAME}`}
        >
          −
        </button>
        <span className="tabular w-10 text-center text-sm font-semibold text-ink" aria-live="polite">{line.QTY1}</span>
        <button
          className="grid size-8 place-items-center rounded-r-lg text-ink-2 hover:bg-surface-2 disabled:opacity-30"
          disabled={disabled || line.QTY1 >= line.QTY_MAX}
          onClick={() => onSet(line.QTY1 + 1)}
          aria-label={`Αύξηση ποσότητας ${line.ITEM_NAME}`}
        >
          +
        </button>
      </div>
      <span className="text-xs text-muted">
        {unitLabel(line.UNIT, line.QTY1)}
        {changed && <> · πρόταση {line.QTY_RECOMMENDED}</>}
      </span>
    </div>
  );
}

type Phase = { kind: "idle" } | { kind: "review" } | { kind: "posting" } | { kind: "error"; message: string };

export function SuggestionCard({ s, onChange, showCustomerLink = true }: { s: Suggestion; onChange: (s: Suggestion) => void; showCustomerLink?: boolean }) {
  const [busy, setBusy] = useState(false);
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const [err, setErr] = useState<string>();
  const [why, setWhy] = useState<Explanation | "loading" | { error: string }>();
  const editable = OPEN_STATUSES.includes(s.status);

  const refresh = async () => onChange(await api<Suggestion>(`/suggestions/${s.id}`));

  const setQty = async (mtrl: number, qty: number) => {
    setBusy(true);
    setErr(undefined);
    setPhase({ kind: "idle" }); // αλλαγή ποσότητας ακυρώνει ό,τι είχε «διαβαστεί» για έγκριση
    try {
      onChange(await api<Suggestion>(`/suggestions/${s.id}/lines/${mtrl}/quantity`, { method: "POST", json: { qty, version: s.version } }));
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
      if (e instanceof ApiError && e.status === 409) await refresh().catch(() => {});
    } finally {
      setBusy(false);
    }
  };

  /** Ίδια λογική με τη φωνή: πρώτα περίληψη, μετά ρητή επιβεβαίωση → confirm + create-draft (idempotent). */
  const approve = async () => {
    setPhase({ kind: "posting" });
    try {
      const { confirmation_token } = await api<{ confirmation_token: string }>(`/suggestions/${s.id}/confirm`, { method: "POST", json: { version: s.version } });
      await api<{ erp_draft_id: string }>(`/suggestions/${s.id}/create-draft`, {
        method: "POST",
        json: { confirmation_token, idempotency_key: `web:${s.id}:v${s.version}` },
      });
      await refresh();
      setPhase({ kind: "idle" });
    } catch (e) {
      setPhase({ kind: "error", message: e instanceof ApiError ? e.message : String(e) });
      await refresh().catch(() => {});
    }
  };

  const reject = async () => {
    if (!window.confirm(`Απόρριψη της πρότασης για ${shortCustomer(s.CUSTOMER_NAME)};`)) return;
    setBusy(true);
    try {
      onChange(await api<Suggestion>(`/suggestions/${s.id}/cancel`, { method: "POST", json: {} }));
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const toggleWhy = async () => {
    if (why && why !== "loading") return setWhy(undefined);
    setWhy("loading");
    try {
      setWhy(await api<Explanation>(`/suggestions/${s.id}/explanation`));
    } catch (e) {
      setWhy({ error: e instanceof ApiError ? e.message : String(e) });
    }
  };

  return (
    <article id={s.id} className="min-w-0 scroll-mt-24 rounded-xl bg-surface ring-1 ring-line target:ring-2 target:ring-series">
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-4 py-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <UrgencyBadge urgency={s.urgency} />
            {showCustomerLink ? (
              <Link href={`/customers/${s.TRDR}`} className="truncate text-base font-semibold text-ink hover:underline">{shortCustomer(s.CUSTOMER_NAME)}</Link>
            ) : (
              <span className="text-base font-semibold text-ink">{shortCustomer(s.CUSTOMER_NAME)}</span>
            )}
            <SuggestionStatusBadge status={s.status} />
          </div>
          <div className="mt-0.5 text-xs text-muted">
            {s.CUSTOMER_CATEGORY} · {s.AREA} · {s.SALESMAN_NAME} · {s.id} v{s.version}
          </div>
        </div>
        <div className="text-right">
          <div className="text-xs text-muted">Παράδοση</div>
          <div className="text-sm font-semibold text-ink">{fmtDateLong(s.SUGGESTED_DELIVERY_DATE)}</div>
        </div>
      </header>

      <div className="divide-y divide-line">
        {s.LINES.map((l) => (
          <div key={l.MTRL} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
            <div className="min-w-0 flex-1">
              <div className="text-sm font-medium text-ink">{l.ITEM_NAME}</div>
              <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-2">
                <span>Εξάντληση <b className="font-medium text-ink">{fmtDate(l.PREDICTED_DEPLETION_DATE)}</b></span>
                <ConfidenceBar value={l.CONFIDENCE} />
              </div>
              <EvidenceChips line={l} />
            </div>
            <QtyStepper line={l} disabled={!editable || busy || phase.kind === "posting"} onSet={(q) => setQty(l.MTRL, q)} />
          </div>
        ))}
      </div>

      {why && (
        <div className="border-t border-line bg-surface-2/60 px-4 py-3 text-sm text-ink-2">
          {why === "loading" ? (
            "Φόρτωση εξήγησης…"
          ) : "error" in why ? (
            <span className="text-critical">{why.error}</span>
          ) : (
            <>
              <p className="leading-relaxed text-ink">{why.text}</p>
              <p className="mt-1.5 text-xs text-muted">
                {why.source === "llm" ? `Κείμενο από LLM${why.model ? ` (${why.model})` : ""}` : "Κείμενο από πρότυπο"} · αριθμοί μόνο από:{" "}
                {why.grounded_on.join(", ")}
              </p>
            </>
          )}
        </div>
      )}

      {err && <div className="px-4 pb-1 pt-3"><ErrorBox error={{ message: err }} /></div>}
      {phase.kind === "error" && (
        <div className="px-4 pb-1 pt-3">
          <ErrorBox error={{ message: `Δεν δημιουργήθηκε draft: ${phase.message}` }} />
        </div>
      )}

      {phase.kind === "review" && (
        <div className="m-4 rounded-lg bg-tint-warning p-4 ring-1 ring-line">
          <p className="text-sm font-semibold text-ink">Επιβεβαίωση draft στο ERP</p>
          <ul className="mt-2 space-y-1 text-sm text-ink">
            {s.LINES.map((l) => (
              <li key={l.MTRL} className="flex justify-between gap-4">
                <span>{l.ITEM_NAME}</span>
                <b className="tabular whitespace-nowrap">{l.QTY1} {unitLabel(l.UNIT, l.QTY1)}</b>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-ink-2">Παράδοση {fmtDateLong(s.SUGGESTED_DELIVERY_DATE)}. Δημιουργείται <b>draft</b>, όχι τελική παραγγελία.</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <button className={btn.primary} onClick={approve}>Ναι, δημιουργία draft</button>
            <button className={btn.secondary} onClick={() => setPhase({ kind: "idle" })}>Άκυρο</button>
          </div>
        </div>
      )}

      <footer className="flex flex-wrap items-center justify-between gap-2 border-t border-line px-4 py-3">
        <button className={btn.ghost} onClick={toggleWhy} aria-expanded={Boolean(why)}>
          {why ? "Απόκρυψη εξήγησης" : "Γιατί; (εξήγηση)"}
        </button>
        {s.status === "draft_created" ? (
          <span className="inline-flex items-center gap-2 rounded-lg bg-tint-good px-3 py-1.5 text-sm font-medium text-good-ink ring-1 ring-line">
            <span aria-hidden>✓</span> Draft στο ERP: <code className="tabular">{s.erp_draft_id}</code>
          </span>
        ) : editable ? (
          <div className="flex gap-2">
            <button className={btn.secondary} onClick={reject} disabled={busy || phase.kind === "posting"}>Απόρριψη</button>
            <button className={btn.primary} onClick={() => setPhase({ kind: "review" })} disabled={busy || phase.kind !== "idle" && phase.kind !== "error"}>
              {phase.kind === "posting" ? "Αποστολή στο ERP…" : "Έγκριση → draft"}
            </button>
          </div>
        ) : null}
      </footer>
    </article>
  );
}
