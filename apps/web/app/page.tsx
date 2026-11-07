"use client";
import Link from "next/link";
import { useMemo, useState } from "react";
import { DayColumns } from "@/components/charts/DayColumns";
import { Briefing } from "@/components/AiText";
import { CallStatusBadge } from "@/components/CallStatus";
import { Card, ErrorBox, Loading, PageHeader, StatTile, UrgencyBadge } from "@/components/ui";
import {
  apiPost, useApi, type Call, type Evaluation, type RiskRow, type Salesman, type Suggestion,
} from "@/lib/api";
import { useToast } from "@/components/Toast";
import { CUTOFF, fmt1, fmtDay, fmtDayLong, fmtEur, fmtNum } from "@/lib/format";

const DAY = 86_400_000;

export default function Overview() {
  const sugs = useApi<Suggestion[]>("/api/suggestions");
  const risk = useApi<RiskRow[]>("/api/risk?limit=2000");
  const calls = useApi<Call[]>("/api/calls");
  const ev = useApi<Evaluation>("/api/evaluation");
  const salesmen = useApi<Salesman[]>("/api/salesmen");
  const [resetting, setResetting] = useState(false);
  const toast = useToast();

  const stats = useMemo(() => {
    const s = sugs.data ?? [], r = risk.data ?? [];
    const days = Array.from({ length: 14 }, (_, i) => {
      const date = new Date(Date.parse(CUTOFF + "T00:00:00Z") + (i + 1) * DAY).toISOString().slice(0, 10);
      return { date, count: r.filter((x) => x.PREDICTED_DEPLETION_DATE === date).length };
    });
    const bySalesman = new Map<number, { customers: number; items: number; drafts: number; value: number }>();
    for (const x of s) {
      const b = bySalesman.get(x.SALESMAN) ?? { customers: 0, items: 0, drafts: 0, value: 0 };
      b.customers += 1; b.items += x.LINES.length; b.value += x.VALUE ?? 0; if (x.status === "draft_created") b.drafts += 1;
      bySalesman.set(x.SALESMAN, b);
    }
    const upcoming = [...s].filter((x) => x.status !== "draft_created" && x.status !== "cancelled")
      .sort((a, b) => a.SUGGESTED_DELIVERY_DATE.localeCompare(b.SUGGESTED_DELIVERY_DATE)
        || a.LINES[0].PREDICTED_DEPLETION_DATE.localeCompare(b.LINES[0].PREDICTED_DEPLETION_DATE));
    const open = s.filter((x) => ["proposed", "modified", "confirmed", "failed"].includes(x.status));
    return {
      openValue: open.reduce((a, x) => a + (x.VALUE ?? 0), 0),
      draftValue: s.filter((x) => x.status === "draft_created").reduce((a, x) => a + (x.VALUE ?? 0), 0),
      atRiskCustomers: new Set(r.filter((x) => (x.days_left ?? 99) <= 7).map((x) => x.TRDR)).size,
      items7: r.filter((x) => (x.days_left ?? 99) <= 7).length,
      pending: s.filter((x) => ["proposed", "modified", "confirmed", "failed"].includes(x.status)).length,
      drafts: s.filter((x) => x.status === "draft_created").length,
      days, bySalesman, upcoming: upcoming.slice(0, 6),
    };
  }, [sugs.data, risk.data]);

  const error = sugs.error ?? risk.error;
  if (error) return <ErrorBox message={error} />;
  if (!sugs.data || !risk.data) return <Loading />;

  const cur = ev.data?.rows.find((r) => r.model === ev.data!.default_model);
  const names = new Map((salesmen.data ?? []).map((x) => [x.PRSN, x.NAME]));

  async function reset() {
    if (!confirm("Επαναφορά demo: όλες οι προτάσεις γυρνούν σε «Προς έγκριση» και σβήνουν οι κλήσεις. Συνέχεια;")) return;
    setResetting(true);
    try {
      const r = await apiPost<{ suggestions: number }>("/api/admin/reset");
      sugs.reload(); calls.reload();
      toast({ kind: "success", title: "Το demo επανήλθε", text: `${fmtNum(r.suggestions)} προτάσεις «Προς έγκριση», καμία κλήση.` });
    } catch (e) { toast({ kind: "error", title: "Η επαναφορά απέτυχε", text: (e as Error).message }); }
    finally { setResetting(false); }
  }

  return (
    <>
      <PageHeader eyebrow={fmtDayLong("2026-11-01") + " 2026 · σενάριο"} title="Επισκόπηση"
        subtitle="Ποιοι πελάτες κινδυνεύουν να ξεμείνουν τις επόμενες μέρες, και τι προτείνουμε να τους στείλουμε.">
        <button className="btn btn-ghost" onClick={reset} disabled={resetting}>{resetting ? "Επαναφορά…" : "Επαναφορά demo"}</button>
      </PageHeader>

      <div className="reveal mb-6">
        <Briefing salesmen={salesmen.data ?? []} />
      </div>

      <div className="reveal grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile hero label="Πελάτες σε κίνδυνο" value={fmtNum(stats.atRiskCustomers)}
          note={`${fmtNum(stats.items7)} είδη τελειώνουν μέσα σε 7 μέρες`} />
        <StatTile label="Αξία προτάσεων προς έγκριση" value={fmtEur(stats.openValue)}
          note="καθαρή αξία με τιμές καταλόγου — πωλήσεις που κινδυνεύουν να χαθούν" />
        <StatTile label="Παραγγελίες προς έγκριση" value={fmtNum(stats.pending)}
          note={<>{fmtNum(stats.drafts)} στο ERP ({fmtEur(stats.draftValue)}) · <Link className="underline" href="/orders">άνοιγμα</Link></>} />
        <StatTile label="Ακρίβεια μοντέλου" value={cur ? <>{fmt1(cur.mae)} <span className="text-base font-normal text-ink-2">μέρες MAE</span></> : "–"}
          note={<Link className="underline" href="/evaluation">baseline 11,3 · λεπτομέρειες</Link>} />
      </div>

      <div className="reveal mt-6 grid gap-6 lg:grid-cols-5">
        <Card className="lg:col-span-3" title="Εξαντλήσεις ανά μέρα" subtitle="Πόσα είδη πελατών τελειώνουν κάθε μέρα, επόμενες 14 μέρες">
          <DayColumns days={stats.days} />
        </Card>
        <Card className="lg:col-span-2" title="Επόμενες παραδόσεις" action={<Link href="/orders" className="text-sm text-ink-2 hover:text-ink">Όλες →</Link>}>
          <ul className="-my-1 divide-y divide-[var(--grid)]">
            {stats.upcoming.map((s) => (
              <li key={s.id} className="py-2.5">
                <Link href={`/customers/${s.TRDR}`} className="group flex items-center justify-between gap-3">
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium text-ink group-hover:underline">{s.CUSTOMER_NAME}</span>
                    <span className="block text-xs text-ink-muted">{s.LINES.length} είδη · πρώτο τελειώνει {fmtDay(s.LINES[0].PREDICTED_DEPLETION_DATE)}</span>
                  </span>
                  <span className="shrink-0 text-right">
                    <span className="block text-sm font-semibold text-ink tnum">{fmtDay(s.SUGGESTED_DELIVERY_DATE)}</span>
                    <span className="block text-xs text-ink-muted tnum">{fmtEur(s.VALUE)}</span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <div className="reveal mt-6 grid gap-6 lg:grid-cols-5">
        <Card className="lg:col-span-3" title="Ανά πωλητή" subtitle="Ποιος έχει τους περισσότερους πελάτες σε κίνδυνο">
          <div className="overflow-x-auto">
            <table className="data">
              <thead><tr><th>Πωλητής</th><th className="num">Πελάτες με πρόταση</th><th className="num">Είδη</th><th className="num">Αξία</th><th className="num">Στο ERP</th><th /></tr></thead>
              <tbody>
                {[...stats.bySalesman.entries()].sort((a, b) => b[1].customers - a[1].customers).map(([id, b]) => (
                  <tr key={id}>
                    <td className="text-ink">{names.get(id) ?? id}</td>
                    <td className="num">{fmtNum(b.customers)}</td>
                    <td className="num">{fmtNum(b.items)}</td>
                    <td className="num">{fmtEur(b.value)}</td>
                    <td className="num">{fmtNum(b.drafts)}</td>
                    <td className="num whitespace-nowrap"><Link href={`/risk?salesman=${id}`} className="text-sm text-ink-2 hover:text-ink">At Risk →</Link></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
        <Card className="lg:col-span-2" title="Τελευταίες κλήσεις" action={<Link href="/voice" className="text-sm text-ink-2 hover:text-ink">Κλήσεις →</Link>}>
          {(calls.data ?? []).length === 0 ? (
            <p className="text-sm text-ink-2">Καμία κλήση ακόμη. Ο voice agent τηλεφωνεί στον πωλητή, εξηγεί τις προτάσεις και φτιάχνει draft με φωνητική επιβεβαίωση.</p>
          ) : (
            <ul className="-my-1 divide-y divide-[var(--grid)]">
              {calls.data!.slice(0, 4).map((c) => (
                <li key={c.call_sid} className="flex items-center justify-between gap-3 py-2.5 text-sm">
                  <span className="min-w-0">
                    <span className="block truncate text-ink">{c.salesman ? names.get(c.salesman) ?? c.salesman : "—"}</span>
                    <span className="block truncate text-xs text-ink-muted">{c.transcript.at(-1)?.text ?? c.call_sid}</span>
                  </span>
                  <CallStatusBadge status={c.status} />
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <div className="reveal mt-6">
        <Card title="Πιο επείγοντα είδη" subtitle="Τελειώνουν μέσα στις επόμενες 3 μέρες" action={<Link href="/risk" className="text-sm text-ink-2 hover:text-ink">At Risk →</Link>}>
          <div className="flex flex-wrap gap-2">
            {risk.data.filter((r) => (r.days_left ?? 99) <= 3).slice(0, 18).map((r) => (
              <Link key={`${r.TRDR}-${r.MTRL}`} href={`/customers/${r.TRDR}`}
                className="lift card !rounded-xl px-3 py-2 text-xs" title={`${r.CUSTOMER_NAME} · ${r.ITEM_NAME}`}>
                <span className="block max-w-[220px] truncate font-medium text-ink">{r.ITEM_NAME}</span>
                <span className="flex items-center gap-2 text-ink-muted"><span className="truncate max-w-[150px]">{r.CUSTOMER_NAME}</span> · {fmtDay(r.PREDICTED_DEPLETION_DATE)}</span>
              </Link>
            ))}
          </div>
          <div className="mt-3"><UrgencyBadge urgency="high" /> <span className="ml-1 text-xs text-ink-muted">= εξάντληση μέσα σε 7 μέρες</span></div>
        </Card>
      </div>
    </>
  );
}
