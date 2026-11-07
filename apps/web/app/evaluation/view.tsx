"use client";

import { MaeBars } from "@/components/charts/mae-bars";
import { Card, ErrorBox, PageHeader, Skeleton } from "@/components/ui";
import { useApi } from "@/lib/api";
import { evaluationSource as sourceLabel, fmtDate, fmtNum, fmtPct } from "@/lib/format";
import type { Evaluation } from "@/lib/types";

export default function EvaluationView() {
  const { data, error, reload } = useApi<Evaluation>("/evaluation");
  const src = data ? sourceLabel(data.source) : null;

  return (
    <>
      <PageHeader
        title="Αξιολόγηση μοντέλου"
        subtitle="Πόσες ημέρες απέχει κατά μέσο όρο η πρόβλεψη εξάντλησης από την πραγματική, με τον κανόνα βαθμολόγησης της Revival."
      />
      {error && <div className="mb-4"><ErrorBox error={error} onRetry={reload} /></div>}
      {src && (
        <div className={`mb-4 rounded-lg px-4 py-3 text-sm text-ink ring-1 ring-line ${src.tone === "warning" ? "bg-tint-warning" : "bg-tint-info"}`}>
          <span aria-hidden className="mr-1.5">{src.tone === "warning" ? "⚠" : "ⓘ"}</span>
          {src.text}
          {data!.cutoffs.length > 0 && <span className="text-ink-2"> Cutoffs: {data!.cutoffs.map((c) => `${fmtDate(c)} ${c.slice(0, 4)}`).join(" · ")}.</span>}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-5">
        <Card className="lg:col-span-3" title="Μέσο απόλυτο σφάλμα (MAE) ανά μοντέλο">
          <div className="p-4">{!data ? <Skeleton className="h-40" /> : <MaeBars rows={data.rows} />}</div>
        </Card>
        <Card className="lg:col-span-2" title="Τι σημαίνουν οι δείκτες">
          <dl className="space-y-3 p-4 text-sm">
            <div><dt className="font-medium text-ink">MAE</dt><dd className="text-ink-2">Μέσο σφάλμα σε ημέρες ανάμεσα σε πρόβλεψη και πραγματική εξάντληση. Το απλό baseline της Revival έχει ~16,1.</dd></div>
            <div><dt className="font-medium text-ink">εντός ±3 / ±7</dt><dd className="text-ink-2">Ποσοστό ζευγών όπου πέσαμε μέσα σε 3 / 7 ημέρες.</dd></div>
            <div><dt className="font-medium text-ink">At Risk P / R</dt><dd className="text-ink-2">Από όσα δηλώσαμε «εξάντληση ≤ 14 ημέρες», πόσα ήταν σωστά (P)· από όσα ήταν πραγματικά, πόσα πιάσαμε (R).</dd></div>
          </dl>
        </Card>
      </div>

      <Card className="mt-4" title="Όλοι οι δείκτες">
        {!data ? (
          <div className="p-4"><Skeleton className="h-32" /></div>
        ) : (
          <div className="overflow-x-auto">
            <table className="tabular w-full min-w-[620px] text-sm">
              <thead>
                <tr className="border-b border-line text-left text-xs font-medium text-muted">
                  <th className="px-4 py-2.5">Μοντέλο</th>
                  <th className="px-4 py-2.5 text-right">MAE (ημ.)</th>
                  <th className="px-4 py-2.5 text-right">εντός ±3</th>
                  <th className="px-4 py-2.5 text-right">εντός ±7</th>
                  <th className="px-4 py-2.5 text-right">At Risk P</th>
                  <th className="px-4 py-2.5 text-right">At Risk R</th>
                </tr>
              </thead>
              <tbody>
                {data.rows.map((r) => (
                  <tr key={r.model} className="border-b border-line last:border-0">
                    <td className="px-4 py-2.5 text-ink">{r.model}</td>
                    <td className="px-4 py-2.5 text-right text-ink">{fmtNum(r.mae)}</td>
                    <td className="px-4 py-2.5 text-right text-ink-2">{fmtPct(r.within_3)}</td>
                    <td className="px-4 py-2.5 text-right text-ink-2">{fmtPct(r.within_7)}</td>
                    <td className="px-4 py-2.5 text-right text-ink-2">{fmtPct(r.at_risk_precision)}</td>
                    <td className="px-4 py-2.5 text-right text-ink-2">{fmtPct(r.at_risk_recall)}</td>
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
