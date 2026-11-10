"use client";
import { useEffect, useRef, useState } from "react";
import { Card, Chip, Segmented } from "@/components/ui";
import { useToast } from "@/components/Toast";
import { apiPost, apiPut, type ContactsState, type Customer } from "@/lib/api";

// Επαφές πελατών (apps/api/app/contacts.py). Τα δεδομένα του ERP δεν έχουν κινητά/email: τα ανεβάζει ο χρήστης.
// demo = όλα τα SMS στο demo κινητό· πραγματικά (live) = στο κινητό του ίδιου του πελάτη, μόνο με ρητή επιβεβαίωση.

interface ImportReport extends ContactsState { imported: number; skipped_empty: number; error_count: number; errors: { row: number; error: string }[] }

function download(name: string, text: string) {
  const url = URL.createObjectURL(new Blob(["﻿" + text], { type: "text/csv;charset=utf-8" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  a.click();
  URL.revokeObjectURL(url);
}

export function ContactsPanel({ state, customers, onChanged }: { state: ContactsState; customers: Customer[]; onChanged: () => void }) {
  const toast = useToast();
  const file = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState<ImportReport | null>(null);
  const [confirmLive, setConfirmLive] = useState(false);

  function template() {
    const q = (s: string) => `"${s.replaceAll('"', '""')}"`;
    download("vora_epafes_pelaton.csv",
      ["TRDR;CODE;NAME;PHONE;EMAIL", ...customers.map((c) => `${c.TRDR};${c.CODE};${q(c.NAME)};;`)].join("\n"));
  }

  async function upload(f: File) {
    setBusy(true);
    try {
      const text = await f.text();
      if (text.length > 60_000) throw new Error("Το αρχείο είναι πολύ μεγάλο (ως ~1.500 γραμμές).");
      const r = await apiPost<ImportReport>("/api/contacts/import", { csv: text });
      setReport(r);
      toast({ kind: r.error_count ? "info" : "success", title: `Μπήκαν ${r.imported} επαφές`, text: r.error_count ? `${r.error_count} γραμμές δεν μπήκαν — δες γιατί από κάτω.` : undefined });
      onChanged();
    } catch (e) {
      toast({ kind: "error", title: "Δεν ανέβηκε", text: (e as Error).message });
    } finally {
      setBusy(false);
      if (file.current) file.current.value = "";
    }
  }

  async function setMode(mode: "demo" | "live", confirm = false) {
    if (mode === state.mode) return;
    if (mode === "live" && !confirm) { setConfirmLive(true); return; }
    try {
      await apiPut("/api/contacts/mode", { mode, confirm });
      toast({ kind: "success", title: mode === "live" ? "Πραγματική αποστολή: ενεργή" : "Πίσω σε demo" });
      setConfirmLive(false);
      onChanged();
    } catch (e) {
      toast({ kind: "error", title: "Δεν άλλαξε", text: (e as Error).message });
    }
  }

  async function clear() {
    if (!window.confirm("Να σβηστούν ΟΛΑ τα κινητά και τα email των πελατών; Η αποστολή γυρνά σε demo.")) return;
    try {
      await apiPost("/api/contacts/clear");
      setReport(null);
      toast({ kind: "success", title: "Οι επαφές σβήστηκαν" });
      onChanged();
    } catch (e) {
      toast({ kind: "error", title: "Δεν σβήστηκαν", text: (e as Error).message });
    }
  }

  return (
    <Card className="fade-in mb-5" title="Επαφές πελατών"
      subtitle="Το ERP δεν δίνει κινητά και email. Ανέβασέ τα εδώ (CSV) ή πρόσθεσέ τα ένα-ένα με το ✎. Μένουν μόνο σε αυτόν τον υπολογιστή."
      action={<Segmented label="Αποστολή SMS" value={state.mode} onChange={(m) => setMode(m)} options={[
        { value: "demo", label: "Demo" }, { value: "live", label: "Πραγματικά" },
      ]} />}>
      <div className="flex flex-wrap items-center gap-2 text-sm text-ink-2">
        <Chip>📱 {state.with_phone}/{state.total_customers} με κινητό</Chip>
        <Chip>✉ {state.with_email}/{state.total_customers} με email</Chip>
        <span>
          {state.mode === "live"
            ? <><strong className="text-ink">Πραγματικά:</strong> κάθε SMS πάει στο κινητό του πελάτη. Πελάτης χωρίς κινητό δεν παίρνει SMS.</>
            : <><strong className="text-ink">Demo:</strong> όλα τα SMS πάνε στο {state.demo_to ?? "— (λείπει το SMS_DEMO_TO στο .env)"}, κανένα σε πελάτη.</>}
        </span>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <button type="button" className="btn btn-sm" onClick={template}>⬇ Πρότυπο CSV με τους πελάτες</button>
        <button type="button" className="btn btn-primary btn-sm" onClick={() => file.current?.click()} disabled={busy}>
          {busy ? "Ανεβαίνει…" : "⬆ Ανέβασμα CSV"}
        </button>
        <input ref={file} type="file" accept=".csv,text/csv" className="sr-only" aria-label="Αρχείο CSV με επαφές"
          onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
        {(state.with_phone > 0 || state.with_email > 0) && <button type="button" className="btn btn-ghost btn-sm" onClick={clear}>Σβήσιμο όλων</button>}
      </div>
      <p className="mt-2 text-xs text-ink-muted">
        Στήλες: <code>TRDR</code> ή <code>CODE</code>, και <code>PHONE</code> ή/και <code>EMAIL</code> (διαχωριστικό «;» ή «,»). Κινητό με 10 ψηφία (69…) ή με +30.
        Κενό κελί δεν σβήνει ό,τι υπάρχει ήδη.
      </p>

      {report && report.error_count > 0 && (
        <div className="mt-3 rounded-xl border border-line bg-surface-2 p-3 text-sm" role="status">
          <div className="font-medium text-ink">{report.error_count} γραμμές δεν μπήκαν:</div>
          <ul className="mt-1 space-y-0.5 text-ink-2">
            {report.errors.map((e) => <li key={e.row} className="tnum">γραμμή {e.row}: {e.error}</li>)}
            {report.error_count > report.errors.length && <li className="text-ink-muted">και άλλες {report.error_count - report.errors.length}</li>}
          </ul>
        </div>
      )}

      {confirmLive && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 p-4 backdrop-blur-[3px]" role="presentation" onClick={() => setConfirmLive(false)}>
          <div className="card w-full max-w-md p-5" role="alertdialog" aria-modal aria-label="Πραγματική αποστολή SMS" onClick={(e) => e.stopPropagation()}>
            <h2 className="text-base font-semibold text-ink">Να σταλούν SMS σε πραγματικούς πελάτες;</h2>
            <p className="mt-2 text-sm text-ink-2">
              Από εδώ και πέρα το κουμπί «📱 SMS» στα Campaigns στέλνει στο <strong className="text-ink">κινητό του ίδιου του πελάτη</strong> ({state.with_phone} πελάτες έχουν κινητό).
              Κάθε SMS φεύγει πάντα με δικό σου πάτημα, ένα-ένα. Γυρνάς σε Demo όποτε θέλεις.
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button type="button" className="btn" onClick={() => setConfirmLive(false)}>Άκυρο</button>
              <button type="button" className="btn btn-primary" onClick={() => setMode("live", true)}>Ναι, πραγματικά</button>
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}

/** Επεξεργασία μίας επαφής. Το κινητό που υπάρχει φαίνεται μασκαρισμένο· για αλλαγή το γράφεις ξανά ολόκληρο. */
export function ContactEdit({ customer, onClose, onSaved }: { customer: Customer; onClose: () => void; onSaved: () => void }) {
  const toast = useToast();
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState(customer.contact?.email ?? "");
  const [keepPhone, setKeepPhone] = useState(!!customer.contact?.phone);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [onClose]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      // πεδίο που δεν στέλνεται μένει ως έχει: το υπάρχον κινητό δεν ξαναγράφεται (το βλέπουμε μόνο μασκαρισμένο)
      const body: { phone?: string | null; email: string | null } = { email: email.trim() || null };
      if (!keepPhone || phone.trim()) body.phone = phone.trim() || null;
      await apiPut(`/api/contacts/${customer.TRDR}`, body);
      toast({ kind: "success", title: "Η επαφή αποθηκεύτηκε", text: customer.NAME });
      onSaved();
      onClose();
    } catch (err) {
      toast({ kind: "error", title: "Δεν αποθηκεύτηκε", text: (err as Error).message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 p-4 backdrop-blur-[3px]" role="presentation" onClick={onClose}>
      <form className="card w-full max-w-md p-5" role="dialog" aria-modal aria-label="Επαφή πελάτη" onClick={(e) => e.stopPropagation()} onSubmit={save}>
        <div className="text-xs text-ink-muted">Επαφή πελάτη</div>
        <h2 className="mt-0.5 text-base font-semibold text-ink">{customer.NAME}</h2>
        <label className="mt-4 block text-sm text-ink-2">
          Κινητό {keepPhone && <span className="text-ink-muted">(υπάρχει: {customer.contact?.phone})</span>}
          <input className="field mt-1 w-full tnum" inputMode="tel" autoFocus value={phone} onChange={(e) => setPhone(e.target.value)}
            placeholder={keepPhone ? "άφησέ το κενό για να μείνει ίδιο" : "69XXXXXXXX ή +30…"} />
        </label>
        {keepPhone && (
          <button type="button" className="btn btn-ghost btn-sm mt-1" onClick={() => setKeepPhone(false)}>Σβήσιμο κινητού</button>
        )}
        <label className="mt-3 block text-sm text-ink-2">
          Email
          <input className="field mt-1 w-full" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="onoma@etaireia.gr" />
        </label>
        <div className="mt-5 flex justify-end gap-2">
          <button type="button" className="btn" onClick={onClose}>Άκυρο</button>
          <button type="submit" className="btn btn-primary" disabled={busy}>{busy ? "Αποθήκευση…" : "Αποθήκευση"}</button>
        </div>
      </form>
    </div>
  );
}
