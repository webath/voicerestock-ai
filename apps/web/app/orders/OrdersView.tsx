"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  EmptyState, ErrorBox, FilterBar, Loading, Meter, PageHeader, Segmented, Select, StatusBadge, UrgencyBadge,
} from "@/components/ui";
import { ApiError, apiPost, useApi, type Salesman, type Suggestion } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { fmtDay, fmtDayLong, fmtEur, fmtEur2, fmtNum } from "@/lib/format";

type Tab = "todo" | "done" | "all";
const TODO = ["proposed", "modified", "confirmed", "failed"];

export function OrdersView() {
  const params = useSearchParams();
  const sugs = useApi<Suggestion[]>("/api/suggestions");
  const salesmen = useApi<Salesman[]>("/api/salesmen");
  const [tab, setTab] = useState<Tab>("todo");
  const [salesman, setSalesman] = useState("");
  const [q, setQ] = useState("");
  // Τοπικές ενημερώσεις (απαντήσεις του API) πάνω από τη λίστα — χωρίς refetch όλων.
  const [local, setLocal] = useState<Record<string, Suggestion>>({});
  const openId = params.get("open");

  if (sugs.error) return <ErrorBox message={sugs.error} />;
  if (!sugs.data) return <Loading />;

  const list = sugs.data.map((s) => local[s.id] ?? s);
  const needle = q.trim().toLowerCase();
  const rows = list.filter((s) => s.id === openId ||
    (tab === "all" || (tab === "todo" ? TODO.includes(s.status) : s.status === "draft_created"))
    && (!salesman || String(s.SALESMAN) === salesman)
    && (!needle || `${s.CUSTOMER_NAME} ${s.LINES.map((l) => l.ITEM_NAME).join(" ")}`.toLowerCase().includes(needle)))
    .sort((a, b) => Number(b.id === openId) - Number(a.id === openId));   // η παραγγελία από link πρώτη
  const counts = {
    todo: list.filter((s) => TODO.includes(s.status)).length,
    done: list.filter((s) => s.status === "draft_created").length,
  };
  const shownValue = rows.reduce((a, s) => a + (s.VALUE ?? 0), 0);

  return (
    <>
      <PageHeader title="Προτεινόμενες παραγγελίες"
        subtitle="Έλεγξε ποσότητες και στείλε τις παραγγελίες ως draft στο ERP. Τίποτα δεν γίνεται τελική παραγγελία χωρίς έγκριση." />
      <FilterBar>
        <Segmented label="Κατάσταση" value={tab} onChange={setTab}
          options={[{ value: "todo", label: `Προς έγκριση · ${counts.todo}` }, { value: "done", label: `Στο ERP · ${counts.done}` }, { value: "all", label: "Όλες" }]} />
        <Select label="Πωλητής" value={salesman} onChange={setSalesman}
          options={[{ value: "", label: "Όλοι οι πωλητές" }, ...(salesmen.data ?? []).map((s) => ({ value: String(s.PRSN), label: s.NAME }))]} />
        <input type="search" className="field w-60 max-w-full" placeholder="Πελάτης ή είδος" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Αναζήτηση" />
      </FilterBar>

      {rows.length > 0 && (
        <p className="fade-in mb-3 text-sm text-ink-2">
          <strong className="text-ink">{fmtNum(rows.length)}</strong> παραγγελίες · συνολική αξία <strong className="text-ink">{fmtEur(shownValue)}</strong>
          <span className="text-ink-muted"> (καθαρή, τιμές καταλόγου 2026)</span>
        </p>
      )}
      {rows.length === 0 ? (
        <EmptyState title={tab === "done" ? "Καμία παραγγελία στο ERP ακόμη" : "Δεν υπάρχουν παραγγελίες εδώ"}>
          {tab === "done" ? "Εγκρίνετε μια πρόταση από την καρτέλα «Προς έγκριση»." : "Άλλαξε φίλτρα."}
        </EmptyState>
      ) : (
        <div className="reveal space-y-3">
          {rows.slice(0, 60).map((s) => (
            <OrderCard key={s.id} s={s} defaultOpen={s.id === openId} onChange={(n) => setLocal((m) => ({ ...m, [n.id]: n }))} />
          ))}
          {rows.length > 60 && <p className="text-center text-xs text-ink-muted">Εμφανίζονται οι πρώτες 60 — περιόρισε με τα φίλτρα.</p>}
        </div>
      )}
    </>
  );
}

function OrderCard({ s, defaultOpen, onChange }: { s: Suggestion; defaultOpen: boolean; onChange: (s: Suggestion) => void }) {
  const [open, setOpen] = useState(defaultOpen);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const ref = useRef<HTMLElement>(null);
  const toast = useToast();
  const locked = s.status === "draft_created" || s.status === "posting" || s.status === "cancelled";
  const units = s.LINES.reduce((a, l) => a + l.QTY1, 0);
  const changed = s.LINES.some((l) => l.QTY1 !== l.QTY_RECOMMENDED);

  useEffect(() => {
    if (defaultOpen) ref.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [defaultOpen]);

  async function run<T>(label: string, fn: () => Promise<T>) {
    setBusy(label); setErr(null);
    try { return await fn(); } catch (e) {
      const msg = e instanceof ApiError && e.code === "version_conflict" ? "Η πρόταση άλλαξε από αλλού (π.χ. από την κλήση). Ανανέωσε τη σελίδα." : (e as Error).message;
      setErr(msg);
      if (label === "approve") toast({ kind: "error", title: "Δεν δημιουργήθηκε draft", text: msg });
    } finally { setBusy(null); }
  }

  const setQty = (mtrl: number, qty: number) => run("qty", async () => {
    const n = await apiPost<Suggestion>(`/api/suggestions/${s.id}/lines/${mtrl}/quantity`, { qty, version: s.version });
    onChange(n);
  });

  const approve = () => run("approve", async () => {
    const c = await apiPost<{ confirmation_token: string; snapshot: Suggestion }>(`/api/suggestions/${s.id}/confirm`, { version: s.version });
    const d = await apiPost<{ erp_draft_id: string; status: string }>(`/api/suggestions/${s.id}/create-draft`,
      { confirmation_token: c.confirmation_token, idempotency_key: `web:${s.id}:v${c.snapshot.version}` });
    onChange({ ...c.snapshot, status: d.status, erp_draft_id: d.erp_draft_id });
    toast({ kind: "success", title: `Draft στο ERP: ${d.erp_draft_id}`,
      text: `${s.CUSTOMER_NAME} · ${c.snapshot.LINES.length} είδη · ${fmtEur(c.snapshot.VALUE)} · παράδοση ${fmtDayLong(s.SUGGESTED_DELIVERY_DATE)}` });
  });

  const cancel = () => run("cancel", async () => onChange(await apiPost<Suggestion>(`/api/suggestions/${s.id}/cancel`)));

  return (
    <article ref={ref} className="card lift overflow-hidden">
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open}
        className="flex w-full flex-wrap items-center gap-x-5 gap-y-2 px-5 py-4 text-left">
        <span className="min-w-0 basis-full sm:basis-0 sm:flex-1">
          <span className="block truncate font-semibold text-ink">{s.CUSTOMER_NAME}</span>
          <span className="block truncate text-xs text-ink-muted">{s.REASON}</span>
        </span>
        <span className="text-right">
          <span className="block text-sm font-semibold text-ink tnum">{fmtDayLong(s.SUGGESTED_DELIVERY_DATE)}</span>
          <span className="block text-xs text-ink-muted">παράδοση</span>
        </span>
        <span className="text-right sm:w-24">
          <span className="block text-sm font-semibold text-ink tnum">{fmtNum(s.LINES.length)} είδη</span>
          <span className="block text-xs text-ink-muted tnum">{fmtNum(units)} μον. · {fmtEur(s.VALUE)}</span>
        </span>
        <span className="flex flex-1 justify-end gap-2 sm:w-56 sm:flex-none"><UrgencyBadge urgency={s.urgency} /><StatusBadge status={s.status} /></span>
        <span aria-hidden className="text-ink-muted transition-transform duration-300" style={{ transform: open ? "rotate(180deg)" : "none" }}>⌄</span>
      </button>

      <div className="expand" data-open={open} inert={!open}>
        <div>
          <div className="border-t border-[var(--grid)] px-3 pb-5 pt-3 sm:px-5">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-xs text-ink-muted">
              <span>{s.CUSTOMER_CATEGORY} · {s.AREA} · Πωλητής: {s.SALESMAN_NAME}</span>
              <Link href={`/customers/${s.TRDR}`} className="text-ink-2 hover:text-ink">Ιστορικό & εξήγηση →</Link>
            </div>
            <div className="overflow-x-auto">
              <table className="data">
                <thead><tr><th>Είδος</th><th className="hidden sm:table-cell">Τελειώνει</th><th className="hidden sm:table-cell">Confidence</th><th className="num">Ποσότητα</th><th className="num hidden md:table-cell">Αξία</th></tr></thead>
                <tbody>
                  {s.LINES.map((l) => (
                    <tr key={l.MTRL}>
                      <td className="text-ink">{l.ITEM_NAME}
                        <div className="text-xs text-ink-muted">{l.ITEM_CODE}<span className="sm:hidden"> · τελειώνει {fmtDay(l.PREDICTED_DEPLETION_DATE)}</span></div>
                      </td>
                      <td className="hidden whitespace-nowrap tnum sm:table-cell">{fmtDay(l.PREDICTED_DEPLETION_DATE)}</td>
                      <td className="hidden sm:table-cell"><Meter value={l.CONFIDENCE} /></td>
                      <td className="num">
                        <span className="inline-flex items-center gap-1">
                          <button className="btn btn-ghost btn-sm" aria-label={`Λιγότερα ${l.ITEM_NAME}`}
                            disabled={locked || !!busy || l.QTY1 <= l.QTY_MIN} onClick={() => setQty(l.MTRL, l.QTY1 - 1)}>−</button>
                          <span className="inline-block w-14 text-center font-semibold text-ink">
                            {fmtNum(l.QTY1)} <span className="text-xs font-normal text-ink-muted">{l.UNIT}</span>
                          </span>
                          <button className="btn btn-ghost btn-sm" aria-label={`Περισσότερα ${l.ITEM_NAME}`}
                            disabled={locked || !!busy || l.QTY1 >= l.QTY_MAX} onClick={() => setQty(l.MTRL, l.QTY1 + 1)}>+</button>
                        </span>
                        {l.QTY1 !== l.QTY_RECOMMENDED && <div className="text-xs text-ink-muted">πρόταση {fmtNum(l.QTY_RECOMMENDED)}</div>}
                      </td>
                      <td className="num hidden whitespace-nowrap md:table-cell">
                        {fmtEur2(l.LINE_VALUE)}<div className="text-xs text-ink-muted">{fmtEur2(l.PRICE)} / {l.UNIT}</div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
              <div className="text-sm" aria-live="polite">
                {s.status === "draft_created" && (
                  <span className="fade-in inline-flex items-center gap-2 text-ink">
                    <span aria-hidden style={{ color: "var(--good)" }}>✓</span> Draft στο ERP: <code className="font-semibold">{s.erp_draft_id}</code>
                  </span>
                )}
                {s.status === "cancelled" && <span className="text-ink-2">Η πρόταση ακυρώθηκε.</span>}
                {err && <span role="alert" className="text-ink"><span aria-hidden style={{ color: "var(--critical)" }}>!</span> {err}</span>}
                {!locked && !err && <span className="text-ink-muted">{changed ? "Έχεις αλλάξει ποσότητες. " : ""}Η έγκριση στέλνει draft (όχι τελική παραγγελία).</span>}
              </div>
              {!locked && (
                <div className="flex gap-2">
                  <button className="btn btn-ghost" onClick={cancel} disabled={!!busy}>Ακύρωση</button>
                  <button className="btn btn-primary" onClick={approve} disabled={!!busy}>
                    {busy === "approve" ? "Αποστολή στο ERP…" : "Έγκριση & αποστολή στο ERP"}
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </article>
  );
}
