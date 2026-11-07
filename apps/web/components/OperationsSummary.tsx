"use client";
import Link from "next/link";
import { useApi, usePolling, type Operations } from "@/lib/api";
import { fmtEur, fmtNum } from "@/lib/format";

export function OperationsSummary() {
  const st = useApi<Operations>("/api/operations");
  usePolling(st.reload, 5000);
  if (st.error) return <p role="alert" className="mb-5 text-sm text-ink-2">Δεν φορτώθηκαν οι μετρήσεις. <button className="btn btn-ghost btn-sm" onClick={st.reload}>Δοκίμασε ξανά</button></p>;
  if (!st.data) return <p role="status" className="mb-5 text-sm text-ink-2">Φόρτωση μετρήσεων…</p>;
  const m = st.data, c = m.changes;
  return (
    <section aria-label="Μετρήσεις λειτουργίας" className="card mb-6 p-5">
      <h2 className="text-base font-semibold text-ink">Από την πρόταση στην πράξη</h2>
      <dl className="mt-4 grid gap-x-6 gap-y-4 sm:grid-cols-2 lg:grid-cols-4">
        {[
          ["Drafts στο ERP", fmtNum(m.drafts)],
          ["Με αλλαγές πωλητή", fmtNum(m.modified_drafts)],
          ["Καθαρή αξία drafts", fmtEur(m.draft_value_eur)],
          ["Μέση διάρκεια κλήσης", m.average_call_seconds == null ? "Δεν υπάρχει ακόμη μέτρηση" : `${fmtNum(m.average_call_seconds)} δευτ. · ${fmtNum(m.timed_calls)} κλήσεις`],
        ].map(([label, value]) => <div key={label}><dt className="text-sm text-ink-2">{label}</dt><dd className="mt-1 font-semibold text-ink tnum">{value}</dd></div>)}
      </dl>
      <p className="mt-3 max-w-prose text-xs text-ink-2">{m.value_basis}</p>
      {c.at && <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-3 text-sm text-ink-2">
        <p>Στην τελευταία ανανέωση: <strong className="text-ink">{c.new ?? 0} νέες</strong> · {c.changed ?? 0} αλλαγμένες · {c.withdrawn ?? 0} αποσύρθηκαν · {c.handled ?? 0} ήδη χειρισμένες με νέα πρόβλεψη.</p>
        {!!c.ids?.length && <Link href="/orders?changed=1" className="btn btn-ghost btn-sm">Δες νέες και αλλαγμένες προτάσεις</Link>}
      </div>}
    </section>
  );
}
