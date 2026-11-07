"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { salesmanQuery, useSalesman } from "@/components/salesman";
import { Card, CallStatusBadge, ConfidenceBar, Empty, ErrorBox, PageHeader, Skeleton, Stat, UrgencyBadge, btn } from "@/components/ui";
import { ApiError, api, useApi } from "@/lib/api";
import { OPEN_STATUSES, evaluationSource, fmtDate, fmtDaysLeft, fmtNum, fmtTime, shortCustomer } from "@/lib/format";
import type { Call, Evaluation, RiskRow, Suggestion } from "@/lib/types";

export default function OverviewView() {
  const { salesman, name } = useSalesman();
  const risk = useApi<RiskRow[]>(`/risk?limit=1000${salesmanQuery(salesman, "&")}`, { refreshMs: 15_000 });
  const sugs = useApi<Suggestion[]>(`/suggestions${salesmanQuery(salesman)}`, { refreshMs: 10_000 });
  const calls = useApi<Call[]>("/calls", { refreshMs: 5_000 });
  const evaluation = useApi<Evaluation>("/evaluation");
  const [resetting, setResetting] = useState(false);
  const [resetErr, setResetErr] = useState<string>();

  const stats = useMemo(() => {
    const r = (risk.data ?? []).filter((x) => x.days_left != null && x.days_left <= 14);
    const s = sugs.data ?? [];
    return {
      pairs: r.length,
      week: r.filter((x) => (x.days_left ?? 99) <= 7).length,
      customers: new Set(r.map((x) => x.TRDR)).size,
      open: s.filter((x) => OPEN_STATUSES.includes(x.status)).length,
      drafts: s.filter((x) => x.status === "draft_created").length,
      top: [...r].sort((a, b) => (a.days_left ?? 99) - (b.days_left ?? 99)).slice(0, 6),
    };
  }, [risk.data, sugs.data]);

  const myCalls = (calls.data ?? []).filter((c) => salesman == null || c.salesman === salesman);
  const last = myCalls[0];
  const ev = evaluation.data;
  const scored = (ev?.rows ?? []).filter((r) => r.mae != null);
  const best = scored.length ? scored.reduce((a, b) => (b.mae! < a.mae! ? b : a)) : undefined;
  const baseline = scored.find((r) => /baseline/i.test(r.model));

  const reset = async () => {
    if (!window.confirm("Επαναφορά του demo; Οι προτάσεις ξαναφορτώνονται από το μοντέλο και χάνονται αλλαγές, εγκρίσεις και ιστορικό κλήσεων (τα drafts που έχουν ήδη σταλεί στο ERP μένουν εκεί).")) return;
    setResetting(true);
    setResetErr(undefined);
    try {
      await api("/admin/reset", { method: "POST", json: {} });
      risk.reload();
      sugs.reload();
      calls.reload();
    } catch (e) {
      setResetErr(e instanceof ApiError ? e.message : String(e));
    } finally {
      setResetting(false);
    }
  };

  return (
    <>
      <PageHeader
        title="Επισκόπηση"
        subtitle={
          <>
            Από τα τιμολόγια του ERP: ποιοι πελάτες θα ξεμείνουν, τι να τους στείλουμε και πότε
            {salesman != null && <> · πωλητής <b className="font-medium text-ink">{name(salesman)}</b></>}.
          </>
        }
        action={
          <button className={btn.secondary} onClick={reset} disabled={resetting} title="POST /api/admin/reset">
            ↺ {resetting ? "Επαναφορά…" : "Επαναφορά demo"}
          </button>
        }
      />
      {resetErr && <div className="mb-4"><ErrorBox error={{ message: `Η επαναφορά απέτυχε: ${resetErr}` }} /></div>}
      {(risk.error || sugs.error) && <div className="mb-4"><ErrorBox error={(risk.error ?? sugs.error)!} onRetry={() => { risk.reload(); sugs.reload(); }} /></div>}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Ζεύγη At Risk (≤ 14 ημ.)" value={risk.data ? stats.pairs : "…"} hint={risk.data ? `${stats.customers} πελάτες` : undefined} href="/risk" />
        <Stat label="Εξάντληση μέσα στην εβδομάδα" value={risk.data ? stats.week : "…"} hint="≤ 7 ημέρες" href="/risk" />
        <Stat label="Ανοιχτές προτάσεις" value={sugs.data ? stats.open : "…"} hint="περιμένουν έγκριση" href="/orders" />
        <Stat label="Drafts στο ERP" value={sugs.data ? stats.drafts : "…"} hint="από dashboard ή κλήση" href="/orders" />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2" title="Πιο επείγοντα" action={<Link href="/risk" className="text-xs font-medium text-series hover:underline">Όλα →</Link>}>
          {!risk.data ? (
            <div className="p-4"><Skeleton className="h-40" /></div>
          ) : stats.top.length === 0 ? (
            <Empty>Κανένας πελάτης σε κίνδυνο τις επόμενες 14 ημέρες.</Empty>
          ) : (
            <ul className="divide-y divide-line">
              {stats.top.map((r) => (
                <li key={`${r.TRDR}-${r.MTRL}`} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                  <span className="min-w-0">
                    <span className="flex items-center gap-2">
                      <UrgencyBadge urgency={r.urgency} />
                      <Link href={`/customers/${r.TRDR}`} className="truncate text-sm font-medium text-ink hover:underline">{shortCustomer(r.CUSTOMER_NAME)}</Link>
                    </span>
                    <span className="mt-0.5 block text-xs text-ink-2">{r.ITEM_NAME}</span>
                  </span>
                  <span className="text-right">
                    <span className={`tabular block text-sm ${(r.days_left ?? 99) <= 7 ? "font-semibold text-critical" : "text-ink"}`}>{fmtDate(r.PREDICTED_DEPLETION_DATE)}</span>
                    <span className="text-xs text-muted">{fmtDaysLeft(r.days_left)}</span>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <div className="space-y-4">
          <Card title="Τελευταία κλήση" action={<Link href="/voice" className="text-xs font-medium text-series hover:underline">Κλήσεις →</Link>}>
            {!calls.data ? (
              <div className="p-4"><Skeleton className="h-20" /></div>
            ) : !last ? (
              <Empty>Καμία κλήση ακόμα.</Empty>
            ) : (
              <div className="space-y-2 p-4 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium text-ink">{name(last.salesman) || "Άγνωστος"}</span>
                  <CallStatusBadge status={last.status} />
                </div>
                <div className="text-xs text-muted">{fmtTime(last.started_at)} · {last.transcript.length} φράσεις</div>
                {last.erp_draft_ids.length > 0 && <div className="text-xs font-medium text-good-ink">✓ {last.erp_draft_ids.join(", ")}</div>}
                {last.transcript.at(-1) && <p className="line-clamp-3 text-xs text-ink-2">«{last.transcript.at(-1)!.text}»</p>}
              </div>
            )}
          </Card>

          <Card title="Ακρίβεια μοντέλου" action={<Link href="/evaluation" className="text-xs font-medium text-series hover:underline">Λεπτομέρειες →</Link>}>
            {!ev ? (
              <div className="p-4"><Skeleton className="h-20" /></div>
            ) : (
              <div className="p-4">
                <div className="text-xs text-ink-2">Μέσο σφάλμα πρόβλεψης</div>
                <div className="mt-1 text-3xl font-semibold tracking-tight text-ink">{best ? `${fmtNum(best.mae)} ημ.` : "—"}</div>
                <div className="mt-1 text-xs text-muted">
                  {best?.model}
                  {baseline && best && baseline !== best && <> · baseline {fmtNum(baseline.mae)} ημ.</>}
                </div>
                <div className={`mt-3 rounded-md px-2.5 py-1.5 text-xs text-ink ring-1 ring-line ${evaluationSource(ev.source).tone === "warning" ? "bg-tint-warning" : "bg-tint-info"}`}>
                  {evaluationSource(ev.source).text}
                </div>
              </div>
            )}
          </Card>
        </div>
      </div>

      {sugs.data && stats.open > 0 && (
        <Card className="mt-4" title="Προτάσεις που περιμένουν έγκριση" action={<Link href="/orders" className="text-xs font-medium text-series hover:underline">Όλες →</Link>}>
          <ul className="divide-y divide-line">
            {(sugs.data ?? []).filter((s) => OPEN_STATUSES.includes(s.status)).slice(0, 5).map((s) => (
              <li key={s.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                <span className="flex min-w-0 items-center gap-2">
                  <UrgencyBadge urgency={s.urgency} />
                  <Link href={`/orders#${s.id}`} className="truncate text-sm font-medium text-ink hover:underline">{shortCustomer(s.CUSTOMER_NAME)}</Link>
                  <span className="text-xs text-muted">{s.LINES.length} είδη</span>
                </span>
                <span className="flex items-center gap-4">
                  <ConfidenceBar value={Math.min(...s.LINES.map((l) => l.CONFIDENCE ?? 1))} />
                  <span className="text-xs text-ink-2">παράδοση {fmtDate(s.SUGGESTED_DELIVERY_DATE)}</span>
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </>
  );
}
