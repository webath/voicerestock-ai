"use client";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMemo } from "react";
import {
  Card, EmptyState, ErrorBox, FilterBar, Loading, Meter, PageHeader, Segmented, Select, UrgencyBadge,
} from "@/components/ui";
import { useApi, type RiskRow, type Salesman, type Suggestion } from "@/lib/api";
import { fmtDayLong, fmtNum } from "@/lib/format";

type Horizon = "3" | "7" | "14";

export function RiskView() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const risk = useApi<RiskRow[]>("/api/risk?limit=2000");
  const sugs = useApi<Suggestion[]>("/api/suggestions");
  const salesmen = useApi<Salesman[]>("/api/salesmen");

  // Τα φίλτρα ζουν στο URL ώστε να μοιράζονται / να γίνεται link από την Επισκόπηση.
  const f = {
    salesman: params.get("salesman") ?? "",
    type: params.get("type") ?? "",
    area: params.get("area") ?? "",
    horizon: (params.get("h") as Horizon) ?? "7",
    q: params.get("q") ?? "",
  };
  const set = (k: string, v: string) => {
    const p = new URLSearchParams(params.toString());
    if (v) p.set(k, v); else p.delete(k);
    router.replace(`${pathname}?${p.toString()}`, { scroll: false });
  };

  const qtyBy = useMemo(() => {
    const m = new Map<string, { qty: number; unit: string; sid: string }>();
    for (const s of sugs.data ?? []) for (const l of s.LINES) m.set(`${s.TRDR}-${l.MTRL}`, { qty: l.QTY1, unit: l.UNIT, sid: s.id });
    return m;
  }, [sugs.data]);

  const all = risk.data ?? [];
  const types = [...new Set(all.map((r) => r.CUSTOMER_CATEGORY))].sort();
  const areas = [...new Set(all.map((r) => r.AREA))].sort();
  const needle = f.q.trim().toLowerCase();
  const rows = all.filter((r) =>
    (r.days_left ?? 99) <= Number(f.horizon)
    && (!f.salesman || String(r.SALESMAN) === f.salesman)
    && (!f.type || r.CUSTOMER_CATEGORY === f.type)
    && (!f.area || r.AREA === f.area)
    && (!needle || `${r.CUSTOMER_NAME} ${r.ITEM_NAME}`.toLowerCase().includes(needle)));
  const customers = new Set(rows.map((r) => r.TRDR)).size;

  function exportCsv() {
    const head = ["Πελάτης", "Τύπος", "Περιοχή", "Είδος", "Εξάντληση", "Σε μέρες", "Confidence", "Προτεινόμενη ποσότητα", "Μονάδα"];
    const esc = (v: unknown) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const lines = rows.map((r) => {
      const q = qtyBy.get(`${r.TRDR}-${r.MTRL}`);
      return [r.CUSTOMER_NAME, r.CUSTOMER_CATEGORY, r.AREA, r.ITEM_NAME, r.PREDICTED_DEPLETION_DATE, r.days_left,
        Math.round(r.CONFIDENCE * 100) + "%", q?.qty ?? "", q?.unit ?? ""].map(esc).join(";");
    });
    // BOM + «;» ώστε το ελληνικό Excel να το ανοίγει σωστά
    const blob = new Blob(["\ufeff" + [head.map(esc).join(";"), ...lines].join("\r\n")], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `at-risk_${f.salesman || "ολοι"}_${f.horizon}μερες.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  if (risk.error) return <ErrorBox message={risk.error} />;
  if (!risk.data) return <Loading />;

  return (
    <>
      <PageHeader title="At Risk"
        subtitle="Είδη που εκτιμούμε ότι τελειώνουν στον πελάτη. Η ημερομηνία βγαίνει από το ιστορικό τιμολογίων, όχι από απογραφή." />

      <FilterBar>
        <input type="search" className="field w-64 max-w-full" placeholder="Πελάτης ή είδος" value={f.q}
          onChange={(e) => set("q", e.target.value)} aria-label="Αναζήτηση" />
        <Select label="Πωλητής" value={f.salesman} onChange={(v) => set("salesman", v)}
          options={[{ value: "", label: "Όλοι οι πωλητές" }, ...(salesmen.data ?? []).map((s) => ({ value: String(s.PRSN), label: s.NAME }))]} />
        <Select label="Τύπος πελάτη" value={f.type} onChange={(v) => set("type", v)}
          options={[{ value: "", label: "Όλοι οι τύποι" }, ...types.map((t) => ({ value: t, label: t }))]} />
        <Select label="Περιοχή" value={f.area} onChange={(v) => set("area", v)}
          options={[{ value: "", label: "Όλες οι περιοχές" }, ...areas.map((a) => ({ value: a, label: a }))]} />
        <Segmented label="Ορίζοντας" value={f.horizon} onChange={(v) => set("h", v === "7" ? "" : v)}
          options={[{ value: "3", label: "3 μέρες" }, { value: "7", label: "7 μέρες" }, { value: "14", label: "14 μέρες" }]} />
      </FilterBar>

      <div className="fade-in mb-3 flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-ink-2">
          <strong className="text-ink">{fmtNum(rows.length)}</strong> είδη σε <strong className="text-ink">{fmtNum(customers)}</strong> πελάτες
        </p>
        <button type="button" className="btn btn-ghost btn-sm" onClick={exportCsv} disabled={rows.length === 0}>⤓ Εξαγωγή CSV</button>
      </div>

      {rows.length === 0 ? (
        <EmptyState title="Κανένα είδος με αυτά τα φίλτρα">Δοκίμασε μεγαλύτερο ορίζοντα ή άλλον πωλητή.</EmptyState>
      ) : (
        <Card className="fade-in !p-0">
          <div className={`overflow-x-auto ${risk.loading ? "refetching" : ""}`}>
            <table className="data">
              <thead>
                <tr>
                  <th>Πελάτης</th><th>Είδος</th><th>Εξάντληση</th><th className="num">Σε μέρες</th>
                  <th>Confidence</th><th className="num">Πρόταση</th><th>Επείγον</th>
                </tr>
              </thead>
              <tbody>
                {rows.slice(0, 300).map((r) => {
                  const q = qtyBy.get(`${r.TRDR}-${r.MTRL}`);
                  return (
                    <tr key={`${r.TRDR}-${r.MTRL}`}>
                      <td>
                        <Link href={`/customers/${r.TRDR}`} className="font-medium text-ink hover:underline">{r.CUSTOMER_NAME}</Link>
                        <div className="text-xs text-ink-muted">{r.CUSTOMER_CATEGORY} · {r.AREA}</div>
                      </td>
                      <td className="text-ink-2">{r.ITEM_NAME}</td>
                      <td className="whitespace-nowrap tnum">{fmtDayLong(r.PREDICTED_DEPLETION_DATE)}</td>
                      <td className="num font-semibold">{r.days_left}</td>
                      <td><Meter value={r.CONFIDENCE} label="Πιθανότητα η ημερομηνία να πέφτει μέσα σε ±3 μέρες (backtest)" /></td>
                      <td className="num whitespace-nowrap">
                        {q ? <Link href={`/orders?open=${q.sid}`} className="hover:underline">{fmtNum(q.qty)} {q.unit}</Link> : "–"}
                      </td>
                      <td><UrgencyBadge urgency={r.urgency} /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {rows.length > 300 && <p className="border-t border-[var(--grid)] px-4 py-3 text-xs text-ink-muted">Εμφανίζονται τα πρώτα 300 — περιόρισε με τα φίλτρα.</p>}
        </Card>
      )}
    </>
  );
}
