"use client";
import Link from "next/link";
import { useMemo, useState } from "react";
import { AiBadge, CustomerMessage } from "@/components/AiText";
import { PurchaseTimeline } from "@/components/charts/PurchaseTimeline";
import { Card, Chip, ErrorBox, Loading, PageHeader, SkeletonLines, UrgencyBadge } from "@/components/ui";
import {
  useApi, type Customer, type Explanation, type Forecast, type History, type Suggestion, type SuggestionLine,
} from "@/lib/api";
import { FACTOR_LABELS, fmt1, fmtDay, fmtDayLong, fmtEur, fmtNum, fmtPct } from "@/lib/format";

const STATUS_LABEL: Record<string, string> = {
  proposed: "Πρόταση", modified: "Τροποποιημένη", confirmed: "Επιβεβαιωμένη", posting: "Αποστολή στο ERP…",
  draft_created: "Draft στο ERP", failed: "Αποτυχία ERP", cancelled: "Ακυρώθηκε",
};

export function CustomerView({ trdr }: { trdr: number }) {
  const customer = useApi<Customer>(`/api/customers/${trdr}`);
  const forecasts = useApi<Forecast[]>(`/api/forecasts?trdr=${trdr}`);
  const history = useApi<History>(`/api/customers/${trdr}/history`);
  const suggestions = useApi<Suggestion[]>("/api/suggestions");
  const suggestion = useMemo(() => suggestions.data?.find((s) => s.TRDR === trdr) ?? null, [suggestions.data, trdr]);
  const explanation = useApi<Explanation>(suggestion ? `/api/suggestions/${suggestion.id}/explanation` : null);

  const rows = useMemo(
    () => [...(forecasts.data ?? [])].sort((a, b) => (a.days_left ?? 999) - (b.days_left ?? 999)),
    [forecasts.data],
  );
  const [picked, setPicked] = useState<number | null>(null);
  const selected = picked ?? suggestion?.LINES[0]?.MTRL ?? rows[0]?.MTRL ?? null;

  const error = customer.error ?? forecasts.error ?? history.error;
  if (error) return <ErrorBox message={error} />;
  if (!customer.data || !forecasts.data || !history.data) return <Loading />;

  const c = customer.data;
  const fc = rows.find((r) => r.MTRL === selected);
  const line = suggestion?.LINES.find((l) => l.MTRL === selected);
  const series = history.data.items.find((i) => i.MTRL === selected);
  const unit = line?.UNIT ?? "μον.";

  return (
    <>
      <div className="mb-2 text-sm"><Link href="/customers" className="text-ink-2 hover:text-ink">← Πελάτες</Link></div>
      <PageHeader
        title={c.NAME}
        subtitle={<>{c.CODE} · {c.TRDCATEGORY} · {c.CITY}, {c.AREA} · Πωλητής: {c.SALESMAN_NAME}</>}
      >
        <div className="flex flex-wrap gap-2">
          {c.cold_start && <Chip title={`Πρώτη καταχώριση ${c.INSDATE}`}>Νέος πελάτης · από {fmtDay(c.INSDATE)}</Chip>}
          {suggestion ? <UrgencyBadge urgency={suggestion.urgency} /> : <UrgencyBadge urgency="none" />}
        </div>
      </PageHeader>

      <div className="reveal grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2" title={fc ? fc.ITEM_NAME : "Παραλαβές"}
          subtitle={fc?.PREDICTED_DEPLETION_DATE
            ? <>Εκτιμώμενη εξάντληση <strong className="text-ink">{fmtDayLong(fc.PREDICTED_DEPLETION_DATE)}</strong> · confidence {fmtPct(fc.CONFIDENCE)}</>
            : "Καμία εξάντληση μέσα στις επόμενες 90 μέρες"}>
          {series
            ? <PurchaseTimeline points={series.points} unit={unit} depletion={fc?.PREDICTED_DEPLETION_DATE ?? null}
                delivery={line ? suggestion!.SUGGESTED_DELIVERY_DATE : null} />
            : <p className="text-sm text-ink-muted">Δεν υπάρχει ιστορικό για αυτό το είδος.</p>}
          {line && <EvidenceFacts line={line} />}
        </Card>

        <Card title="Προτεινόμενη παραγγελία"
          subtitle={suggestion ? <>Παράδοση <strong className="text-ink">{fmtDayLong(suggestion.SUGGESTED_DELIVERY_DATE)}</strong> · <strong className="text-ink">{fmtEur(suggestion.VALUE)}</strong> · {STATUS_LABEL[suggestion.status] ?? suggestion.status}</> : undefined}>
          {!suggestion ? (
            <p className="text-sm text-ink-2">Κανένα είδος δεν τελειώνει στις επόμενες 3 εβδομάδες — δεν χρειάζεται παραγγελία τώρα.</p>
          ) : (
            <>
              <div className="ai-shine rounded-xl bg-surface-2 p-3 text-sm text-ink-2">
                {explanation.data ? (
                  <>
                    <p className="text-ink">{explanation.data.text}</p>
                    <p className="mt-2 flex items-center gap-2 text-xs text-ink-muted">
                      <AiBadge source={explanation.data.source} />
                      {explanation.data.source === "llm" ? "εξήγηση μόνο από τα στοιχεία της πρόβλεψης" : "από τα στοιχεία της πρόβλεψης"}
                    </p>
                  </>
                ) : explanation.error ? "Η εξήγηση δεν είναι διαθέσιμη." : (
                  <><SkeletonLines lines={4} /><p className="mt-2 text-xs text-ink-muted">Το AI ετοιμάζει εξήγηση από τα στοιχεία της πρόβλεψης…</p></>
                )}
              </div>
              <ul className="mt-4 divide-y divide-[var(--grid)] text-sm">
                {suggestion.LINES.map((l) => (
                  <li key={l.MTRL}>
                    <button type="button" onClick={() => setPicked(l.MTRL)}
                      className={`flex w-full items-baseline justify-between gap-3 py-2 text-left ${l.MTRL === selected ? "font-semibold text-ink" : "text-ink-2 hover:text-ink"}`}>
                      <span>{l.ITEM_NAME}<span className="block text-xs font-normal text-ink-muted">τελειώνει {fmtDay(l.PREDICTED_DEPLETION_DATE)}</span></span>
                      <span className="tnum whitespace-nowrap">{fmtNum(l.QTY1)} {l.UNIT}</span>
                    </button>
                  </li>
                ))}
              </ul>
              {suggestion.erp_draft_id && <p className="mt-3 text-xs text-ink-2"><span aria-hidden style={{ color: "var(--good)" }}>✓</span> ERP draft: <code>{suggestion.erp_draft_id}</code></p>}
              <div className="mt-4 flex flex-wrap gap-2">
                {suggestion.status !== "draft_created" && suggestion.status !== "cancelled" && (
                  <Link href={`/orders?open=${suggestion.id}`} className="btn btn-primary flex-1">Έλεγχος & έγκριση</Link>
                )}
                <Link href={`/voice?salesman=${suggestion.SALESMAN}`} className="btn btn-ghost flex-1">📞 Κάλεσε τον πωλητή</Link>
              </div>
              <CustomerMessage suggestionId={suggestion.id} />
            </>
          )}
        </Card>
      </div>

      <Card className="mt-6" title="Πρόβλεψη ανά είδος" subtitle={`${rows.length} είδη που αγοράζει ο πελάτης · επιλέξτε γραμμή για το γράφημα`}>
        <div className="overflow-x-auto">
          <table className="data">
            <thead>
              <tr>
                <th>Είδος</th>
                <th>Κατηγορία</th>
                <th>Εξάντληση</th>
                <th className="num">Σε μέρες</th>
                <th className="num">Confidence</th>
                <th className="num">Στην πρόταση</th>
                <th>Επείγον</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const l = suggestion?.LINES.find((x) => x.MTRL === r.MTRL);
                return (
                  <tr key={r.MTRL} className="clickable" aria-selected={r.MTRL === selected} tabIndex={0}
                    onClick={() => setPicked(r.MTRL)} onKeyDown={(e) => e.key === "Enter" && setPicked(r.MTRL)}>
                    <td className="text-ink">{r.ITEM_NAME}</td>
                    <td className="text-ink-2">{r.CATEGORY}</td>
                    <td className="tnum">{r.PREDICTED_DEPLETION_DATE ? fmtDay(r.PREDICTED_DEPLETION_DATE) : "–"}</td>
                    <td className="num">{r.days_left ?? "–"}</td>
                    <td className="num">{r.PREDICTED_DEPLETION_DATE ? fmtPct(r.CONFIDENCE) : "–"}</td>
                    <td className="num">{l ? `${fmtNum(l.QTY1)} ${l.UNIT}` : "–"}</td>
                    <td><UrgencyBadge urgency={r.urgency} /></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}

/** Τα στοιχεία που στηρίζουν την πρόβλεψη — ό,τι λέει και ο voice agent. */
function EvidenceFacts({ line }: { line: SuggestionLine }) {
  const e = line.evidence;
  const facts = [
    { label: "Κατανάλωση", value: `${fmt1(e.burn_rate_per_day)} ${line.UNIT}/μέρα`, note: e.burn_rate_recent_per_day != null ? `τελευταίες 90 μέρες: ${fmt1(e.burn_rate_recent_per_day)}` : undefined },
    { label: "Τελευταία παραλαβή", value: `${fmtNum(e.last_purchase_qty)} ${line.UNIT}`, note: fmtDayLong(e.last_purchase_date) },
    { label: "Κύκλος αγορών", value: e.avg_interval_days != null ? `κάθε ${fmtNum(Math.round(e.avg_interval_days))} μέρες` : "–", note: `${fmtNum(e.purchases_count)} αγορές σε 180 μέρες` },
    { label: "Απόθεμα στο cutoff", value: `≈ ${fmt1(e.est_stock_at_cutoff)} ${line.UNIT}`, note: "εκτίμηση" },
  ];
  return (
    <div className="mt-5 border-t border-[var(--grid)] pt-4">
      <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {facts.map((f) => (
          <div key={f.label}>
            <dt className="text-xs text-ink-2">{f.label}</dt>
            <dd className="mt-0.5 font-semibold text-ink">{f.value}</dd>
            {f.note && <dd className="text-xs text-ink-muted">{f.note}</dd>}
          </div>
        ))}
      </dl>
      <div className="mt-4 flex flex-wrap gap-2">
        {e.factors.map((f) => (
          <Chip key={f.name} title={f.source}>
            {FACTOR_LABELS[f.name] ?? f.name}
            {f.impact_days != null && f.impact_days !== 0 ? ` · ${f.impact_days > 0 ? "+" : ""}${fmt1(f.impact_days)} μέρες` : ""}
          </Chip>
        ))}
        {e.seasonal_multiplier != null && (
          <Chip title="Ρυθμός επόμενων 90 ημερών / ρυθμός τελευταίων 90 ημερών">Εποχή ×{fmt1(e.seasonal_multiplier)}</Chip>
        )}
        {e.promo && <Chip title={`${e.promo.from} – ${e.promo.to}`}>Προσφορά −{e.promo.disc_prc}% · {fmtDay(e.promo.from)}–{fmtDay(e.promo.to)}</Chip>}
        {e.peer_group && <Chip>Παρόμοιοι πελάτες: {e.peer_group}</Chip>}
      </div>
      {e.warnings.length > 0 && (
        <ul className="mt-3 space-y-1 text-xs text-ink-2">
          {e.warnings.map((w) => <li key={w}><span aria-hidden style={{ color: "var(--serious)" }}>▲</span> {w}</li>)}
        </ul>
      )}
    </div>
  );
}
