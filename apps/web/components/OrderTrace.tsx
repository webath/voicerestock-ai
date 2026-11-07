"use client";
import { useApi, type OrderTrace as Trace, type OrderEvent, type Suggestion } from "@/lib/api";
import { fmtDay, fmtNum } from "@/lib/format";

function eventTitle(e: OrderEvent) {
  if (e.action.startsWith("quantity ")) return "Αλλαγή ποσότητας";
  return ({ forecast_created: "Δημιουργία πρότασης", forecast_updated: "Νέα πρόβλεψη", forecast_withdrawn: "Απόσυρση πρότασης",
    confirm: "Έγκριση πωλητή", create: "Δημιουργία draft", "create-draft": "Απάντηση ERP", cancel: "Ακύρωση",
    voice_confirmation: "Φωνητική επιβεβαίωση" } as Record<string, string>)[e.action] ?? e.action;
}

function eventDetail(e: OrderEvent) {
  const qty = /^quantity (\d+)=(\d+)$/.exec(e.action);
  if (qty) {
    const l = e.snapshot?.LINES.find((line) => line.MTRL === Number(qty[1]));
    return `${l?.ITEM_NAME ?? `Είδος ${qty[1]}`}: ${qty[2]} ${l?.UNIT ?? "μονάδες"}`;
  }
  return e.outcome;
}

export function OrderTrace({ suggestion }: { suggestion: Suggestion }) {
  const st = useApi<Trace>(`/api/suggestions/${suggestion.id}/trace?v=${suggestion.version}&status=${suggestion.status}`);
  if (st.error) return <p role="alert" className="mt-5 text-sm text-ink-2">Δεν φορτώθηκε η διαδρομή. <button className="btn btn-ghost btn-sm" onClick={st.reload}>Δοκίμασε ξανά</button></p>;
  if (!st.data) return <p role="status" className="mt-5 text-sm text-ink-2">Φόρτωση διαδρομής παραγγελίας…</p>;
  return (
    <details className="mt-5 border-t border-line pt-4">
      <summary className="cursor-pointer text-sm font-semibold text-ink">Διαδρομή παραγγελίας · δεδομένα, πρόβλεψη και εγκρίσεις</summary>
      <div className="mt-4 grid gap-6 lg:grid-cols-2">
        <div className="order-2 lg:order-1">
          <h3 className="text-sm font-semibold text-ink">Πάνω σε ποια δεδομένα βασίστηκε</h3>
          <ul className="mt-2 divide-y divide-[var(--grid)] text-sm">
            {st.data.evidence.map((l) => <li key={l.MTRL} className="py-2">
              <p className="font-medium text-ink">{l.ITEM_NAME}</p>
              <p className="mt-1 text-ink-2">{fmtNum(l.evidence.purchases_count)} αγορές · τελευταία {l.evidence.last_purchase_date ? fmtDay(l.evidence.last_purchase_date) : "χωρίς καταγραφή"} · εκτίμηση εξάντλησης {fmtDay(l.PREDICTED_DEPLETION_DATE)}</p>
              <p className="mt-1 text-ink-2">Πρόταση {fmtNum(l.QTY_RECOMMENDED)} {l.UNIT} · επιλεγμένη ποσότητα {fmtNum(l.QTY1)} {l.UNIT}</p>
              <p className="mt-1 text-xs text-ink-2">Μοντέλο: {l.evidence.model_version ?? "δεν καταγράφηκε"}</p>
              {!!l.evidence.warnings?.length && <p className="mt-1 text-xs text-ink-2">{l.evidence.warnings.join(" · ")}</p>}
            </li>)}
          </ul>
        </div>
        <div className="order-1 lg:order-2">
          <h3 className="text-sm font-semibold text-ink">Τι έγινε και από ποιον</h3>
          {!st.data.events.length ? <p className="mt-2 text-sm text-ink-2">Δεν υπάρχουν καταγεγραμμένα βήματα για αυτή την πρόταση.</p> :
            <ol className="mt-2 space-y-4">
              {st.data.events.map((e, i) => <li key={`${e.at}-${i}`} className="text-sm">
                <p className="font-medium text-ink">{eventTitle(e)}</p>
                <p className="mt-0.5 break-words text-ink-2">{eventDetail(e)}</p>
                {e.snapshot && <p className="mt-0.5 text-xs text-ink-2">Έκδοση {e.snapshot.version} · {e.snapshot.LINES.length} είδη · παράδοση {fmtDay(e.snapshot.SUGGESTED_DELIVERY_DATE)}</p>}
                <p className="mt-0.5 break-all text-xs text-ink-2"><time dateTime={e.at}>{new Date(e.at).toLocaleString("el-GR")}</time> · {e.actor === "dashboard" ? "Dashboard" : e.actor.startsWith("voice:") ? "Φωνητικός agent" : e.actor === "unknown" ? "Χωρίς καταγεγραμμένη προέλευση" : e.actor}</p>
              </li>)}
            </ol>}
          {st.data.erp_draft_id && <p className="mt-4 break-all text-sm font-semibold text-ink">Draft ERP: {st.data.erp_draft_id}</p>}
        </div>
      </div>
    </details>
  );
}
