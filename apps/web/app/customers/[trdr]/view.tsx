"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";
import { PurchaseTimeline } from "@/components/charts/purchase-timeline";
import { SuggestionCard } from "@/components/suggestion-card";
import { Card, ConfidenceBar, Empty, ErrorBox, PageHeader, Skeleton, Stat, UrgencyBadge } from "@/components/ui";
import { useApi } from "@/lib/api";
import { SCENARIO_TODAY, URGENCY, daysBetween, fmtDate, fmtDaysLeft, shortCustomer } from "@/lib/format";
import type { Forecast, History, RiskRow, Suggestion } from "@/lib/types";

export default function CustomerView() {
  const { trdr } = useParams<{ trdr: string }>();
  const forecasts = useApi<Forecast[]>(`/forecasts?trdr=${trdr}`);
  const history = useApi<History>(`/customers/${trdr}/history`);
  const sugs = useApi<Suggestion[]>("/suggestions", { refreshMs: 15_000 });
  const risk = useApi<RiskRow[]>("/risk?limit=1000");
  const [picked, setPicked] = useState<number>();
  const [local, setLocal] = useState<Suggestion>();

  const suggestion = useMemo(() => {
    const s = sugs.data?.find((x) => String(x.TRDR) === trdr);
    return local && s && local.id === s.id && local.version >= s.version ? local : s;
  }, [sugs.data, trdr, local]);

  const rows = useMemo(
    () =>
      (forecasts.data ?? [])
        .map((f) => ({ ...f, days: f.days_left ?? (f.PREDICTED_DEPLETION_DATE ? daysBetween(SCENARIO_TODAY, f.PREDICTED_DEPLETION_DATE) : null) }))
        .sort((a, b) => (a.days ?? 999) - (b.days ?? 999)),
    [forecasts.data],
  );
  const selected = picked ?? rows[0]?.MTRL;
  const sel = rows.find((r) => r.MTRL === selected);
  const item = history.data?.items.find((i) => i.MTRL === selected);
  const line = suggestion?.LINES.find((l) => l.MTRL === selected);
  const unit = line?.UNIT ?? (item?.ITEM_NAME.includes("κιβ") ? "ΚΙΒ" : "ΤΕΜ");

  const riskRow = risk.data?.find((r) => String(r.TRDR) === trdr);
  const name = suggestion?.CUSTOMER_NAME ?? riskRow?.CUSTOMER_NAME;
  const category = suggestion?.CUSTOMER_CATEGORY ?? riskRow?.CUSTOMER_CATEGORY;
  const area = suggestion?.AREA ?? riskRow?.AREA;
  const atRisk = rows.filter((r) => r.days != null && r.days <= 14).length;
  const next = rows.find((r) => r.days != null);

  return (
    <>
      <div className="mb-2 text-sm">
        <Link href="/risk" className="text-ink-2 hover:text-ink">← At Risk</Link>
      </div>
      <PageHeader
        title={name ? shortCustomer(name) : `Πελάτης #${trdr}`}
        subtitle={[category, area, suggestion?.SALESMAN_NAME, suggestion?.CUSTOMER_CODE].filter(Boolean).join(" · ") || `TRDR ${trdr}`}
      />

      {(forecasts.error || history.error) && (
        <div className="mb-4"><ErrorBox error={(forecasts.error ?? history.error)!} onRetry={() => { forecasts.reload(); history.reload(); }} /></div>
      )}

      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Είδη που παρακολουθούνται" value={forecasts.data ? rows.length : "…"} />
        <Stat label="Εξάντληση ≤ 14 ημέρες" value={forecasts.data ? atRisk : "…"} />
        <Stat label="Επόμενη εξάντληση" value={next ? fmtDate(next.PREDICTED_DEPLETION_DATE) : "—"} hint={next ? `${next.ITEM_NAME} · ${fmtDaysLeft(next.days)}` : undefined} />
        <Stat label="Πρόταση παραγγελίας" value={suggestion ? fmtDate(suggestion.SUGGESTED_DELIVERY_DATE) : "—"} hint={suggestion ? `παράδοση · ${suggestion.LINES.length} είδη` : "καμία ανοιχτή"} />
      </div>

      <div className="grid gap-4 lg:grid-cols-5">
        <Card className="min-w-0 lg:col-span-3" title={sel ? `Παραλαβές ανά εβδομάδα — ${sel.ITEM_NAME}` : "Παραλαβές ανά εβδομάδα"}>
          <div className="p-4">
            {!history.data || !forecasts.data ? (
              <Skeleton className="h-56" />
            ) : !item ? (
              <Empty>Δεν υπάρχει ιστορικό για αυτό το είδος.</Empty>
            ) : (
              <PurchaseTimeline
                points={item.points}
                unit={unit}
                today={SCENARIO_TODAY}
                depletion={sel?.PREDICTED_DEPLETION_DATE ?? null}
                delivery={line ? suggestion?.SUGGESTED_DELIVERY_DATE : null}
              />
            )}
          </div>
        </Card>

        <Card className="min-w-0 lg:col-span-2" title="Προβλέψεις ανά είδος" action={<span className="text-xs text-muted">κλικ για γράφημα</span>}>
          {!forecasts.data ? (
            <div className="p-4"><Skeleton className="h-48" /></div>
          ) : rows.length === 0 ? (
            <Empty>Κανένα είδος-στόχος για αυτόν τον πελάτη.</Empty>
          ) : (
            <ul className="max-h-[300px] divide-y divide-line overflow-auto">
              {rows.map((r) => (
                <li key={r.MTRL}>
                  <button
                    onClick={() => setPicked(r.MTRL)}
                    aria-pressed={r.MTRL === selected}
                    className={`flex w-full items-center justify-between gap-3 px-4 py-2.5 text-left transition hover:bg-surface-2/60 ${r.MTRL === selected ? "bg-tint-info" : ""}`}
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-sm text-ink">{r.ITEM_NAME}</span>
                      <span className="mt-0.5 flex items-center gap-2 text-xs text-muted">
                        <UrgencyBadge urgency={r.urgency} /> {r.CATEGORY}
                      </span>
                    </span>
                    <span className="shrink-0 text-right">
                      <span className={`tabular block text-sm ${r.days != null && r.days <= 7 ? "font-semibold text-critical" : "text-ink"}`}>{fmtDate(r.PREDICTED_DEPLETION_DATE)}</span>
                      <ConfidenceBar value={r.CONFIDENCE} />
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <h2 className="mb-3 mt-8 text-sm font-semibold text-ink">Πρόταση παραγγελίας</h2>
      {!sugs.data ? (
        <Skeleton className="h-48" />
      ) : suggestion ? (
        <SuggestionCard s={suggestion} onChange={setLocal} showCustomerLink={false} />
      ) : (
        <div className="rounded-xl bg-surface ring-1 ring-line">
          <Empty>Δεν υπάρχει πρόταση για αυτόν τον πελάτη: {URGENCY.none.label.toLowerCase()} ή εξάντληση αργότερα.</Empty>
        </div>
      )}
    </>
  );
}
