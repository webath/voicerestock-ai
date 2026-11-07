"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { salesmanQuery, useSalesman } from "@/components/salesman";
import { Card, ConfidenceBar, Empty, ErrorBox, PageHeader, Skeleton, UrgencyBadge, input } from "@/components/ui";
import { useApi } from "@/lib/api";
import { URGENCY, fmtDate, fmtDaysLeft, shortCustomer } from "@/lib/format";
import type { RiskRow, Suggestion, Urgency } from "@/lib/types";

export default function RiskView() {
  const { salesman, name } = useSalesman();
  const risk = useApi<RiskRow[]>(`/risk?limit=1000${salesmanQuery(salesman, "&")}`, { refreshMs: 15_000 });
  const sugs = useApi<Suggestion[]>(`/suggestions${salesmanQuery(salesman)}`, { refreshMs: 15_000 });

  const [urgency, setUrgency] = useState<Urgency | "">("");
  const [category, setCategory] = useState("");
  const [area, setArea] = useState("");
  const [minConf, setMinConf] = useState(0);
  const [q, setQ] = useState("");

  // Το /api/risk φέρνει κατηγορία/περιοχή/πωλητή (contract)· για παλιότερο API, συμπλήρωση από την πρόταση του πελάτη.
  const meta = useMemo(() => {
    const m = new Map<number, { category: string; area: string; salesman: number }>();
    for (const s of sugs.data ?? []) m.set(s.TRDR, { category: s.CUSTOMER_CATEGORY, area: s.AREA, salesman: s.SALESMAN });
    for (const r of risk.data ?? [])
      if (r.CUSTOMER_CATEGORY || r.AREA)
        m.set(r.TRDR, { category: r.CUSTOMER_CATEGORY ?? "", area: r.AREA ?? "", salesman: r.SALESMAN ?? m.get(r.TRDR)?.salesman ?? 0 });
    return m;
  }, [sugs.data, risk.data]);

  const rows = useMemo(() => {
    const needle = q.trim().toLocaleLowerCase("el");
    return (risk.data ?? [])
      .map((r) => ({ ...r, ...(meta.get(r.TRDR) ?? { category: "", area: "", salesman: r.SALESMAN ?? 0 }) }))
      .filter((r) => !urgency || r.urgency === urgency)
      .filter((r) => !category || r.category === category)
      .filter((r) => !area || r.area === area)
      .filter((r) => (r.CONFIDENCE ?? 0) >= minConf)
      .filter((r) => !needle || `${r.CUSTOMER_NAME} ${r.ITEM_NAME}`.toLocaleLowerCase("el").includes(needle))
      .sort((a, b) => (a.days_left ?? 999) - (b.days_left ?? 999) || URGENCY[a.urgency].rank - URGENCY[b.urgency].rank);
  }, [risk.data, meta, urgency, category, area, minConf, q]);

  const categories = useMemo(() => [...new Set([...meta.values()].map((m) => m.category))].filter(Boolean).sort(), [meta]);
  const areas = useMemo(() => [...new Set([...meta.values()].map((m) => m.area))].filter(Boolean).sort(), [meta]);
  const customers = new Set(rows.map((r) => r.TRDR)).size;

  return (
    <>
      <PageHeader
        title="Πελάτες At Risk"
        subtitle={
          <>
            Ζεύγη πελάτη × είδους με εξάντληση μέσα σε 14 ημέρες, πιο κοντινή πρώτα
            {salesman != null && <> · πωλητής <b className="font-medium text-ink">{name(salesman)}</b></>}.
          </>
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-2" role="group" aria-label="Φίλτρα">
        <input className={`${input} w-full sm:w-64`} placeholder="Αναζήτηση πελάτη ή είδους…" value={q} onChange={(e) => setQ(e.target.value)} />
        <select className={input} value={urgency} onChange={(e) => setUrgency(e.target.value as Urgency | "")} aria-label="Επείγον">
          <option value="">Κάθε επείγον</option>
          {(["high", "medium", "low"] as Urgency[]).map((u) => (
            <option key={u} value={u}>{URGENCY[u].label}</option>
          ))}
        </select>
        <select className={input} value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Κατηγορία πελάτη">
          <option value="">Κάθε κατηγορία</option>
          {categories.map((c) => <option key={c}>{c}</option>)}
        </select>
        <select className={input} value={area} onChange={(e) => setArea(e.target.value)} aria-label="Περιοχή">
          <option value="">Κάθε περιοχή</option>
          {areas.map((a) => <option key={a}>{a}</option>)}
        </select>
        <select className={input} value={minConf} onChange={(e) => setMinConf(Number(e.target.value))} aria-label="Ελάχιστη βεβαιότητα">
          <option value={0}>Κάθε βεβαιότητα</option>
          <option value={0.5}>Βεβαιότητα ≥ 50%</option>
          <option value={0.75}>Βεβαιότητα ≥ 75%</option>
        </select>
      </div>

      {risk.error && <div className="mb-4"><ErrorBox error={risk.error} onRetry={risk.reload} /></div>}

      <Card
        title={risk.data ? `${rows.length} ζεύγη · ${customers} πελάτες` : "Φόρτωση…"}
        action={<span className="text-xs text-muted">ανανέωση κάθε 15″</span>}
      >
        {!risk.data ? (
          <div className="p-4"><Skeleton className="h-48" /></div>
        ) : rows.length === 0 ? (
          <Empty>Κανένα ζεύγος με αυτά τα φίλτρα.</Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-sm">
              <thead>
                <tr className="border-b border-line text-left text-xs font-medium text-muted">
                  <th className="px-4 py-2.5">Επείγον</th>
                  <th className="px-4 py-2.5">Πελάτης</th>
                  <th className="px-4 py-2.5">Είδος</th>
                  <th className="px-4 py-2.5">Εξάντληση</th>
                  <th className="px-4 py-2.5">Βεβαιότητα</th>
                  <th className="px-4 py-2.5 text-right">Πρόταση</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={`${r.TRDR}-${r.MTRL}`} className="border-b border-line last:border-0 hover:bg-surface-2/60">
                    <td className="px-4 py-3"><UrgencyBadge urgency={r.urgency} /></td>
                    <td className="px-4 py-3">
                      <Link href={`/customers/${r.TRDR}`} className="font-medium text-ink hover:underline">{shortCustomer(r.CUSTOMER_NAME)}</Link>
                      <div className="text-xs text-muted">{[r.category, r.area, salesman == null ? name(r.salesman) : ""].filter(Boolean).join(" · ")}</div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="text-ink-2">{r.ITEM_NAME}</div>
                      {r.CATEGORY && <div className="text-xs text-muted">{r.CATEGORY}</div>}
                    </td>
                    <td className="px-4 py-3">
                      <div className="tabular text-ink">{fmtDate(r.PREDICTED_DEPLETION_DATE)}</div>
                      <div className={`text-xs ${r.days_left != null && r.days_left <= 7 ? "font-medium text-critical" : "text-muted"}`}>{fmtDaysLeft(r.days_left)}</div>
                    </td>
                    <td className="px-4 py-3"><ConfidenceBar value={r.CONFIDENCE} /></td>
                    <td className="px-4 py-3 text-right">
                      {r.suggestion_id ? (
                        <Link href={`/orders#${r.suggestion_id}`} className="text-xs font-medium text-series hover:underline">Άνοιγμα →</Link>
                      ) : (
                        <span className="text-xs text-muted">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
