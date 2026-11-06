"use client";
import Link from "next/link";
import { useState } from "react";
import { CALL_STEPS, CallStatusBadge, isLive, stepIndex } from "@/components/CallStatus";
import { Card, EmptyState, ErrorBox, Loading, PageHeader, Select } from "@/components/ui";
import { apiPost, usePolling, useApi, VOICE_URL, type Call, type Salesman, type Suggestion } from "@/lib/api";
import { fmtNum } from "@/lib/format";

const time = new Intl.DateTimeFormat("el-GR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });

export default function VoicePage() {
  const calls = useApi<Call[]>("/api/calls");
  const salesmen = useApi<Salesman[]>("/api/salesmen");
  const sugs = useApi<Suggestion[]>("/api/suggestions");
  usePolling(calls.reload, 3000);
  const [who, setWho] = useState("");
  const [dialing, setDialing] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  if (calls.error) return <ErrorBox message={calls.error} />;
  if (!calls.data) return <Loading />;

  const names = new Map((salesmen.data ?? []).map((s) => [s.PRSN, s.NAME]));
  const pending = new Map<number, number>();
  for (const s of sugs.data ?? []) if (s.status !== "draft_created" && s.status !== "cancelled") pending.set(s.SALESMAN, (pending.get(s.SALESMAN) ?? 0) + 1);
  const selected = who || String(salesmen.data?.[0]?.PRSN ?? "");

  async function dial() {
    setDialing(true); setMsg(null);
    try {
      await apiPost("/voice/calls", { salesman: Number(selected) }, VOICE_URL);
      setMsg({ ok: true, text: "Η κλήση ξεκίνησε — θα εμφανιστεί παρακάτω σε λίγα δευτερόλεπτα." });
      calls.reload();
    } catch (e) {
      setMsg({ ok: false, text: e instanceof TypeError
        ? `Ο voice agent δεν απαντά στο ${VOICE_URL}. Τρέχει το apps/voice;`
        : (e as Error).message });
    } finally { setDialing(false); }
  }

  return (
    <>
      <PageHeader title="Κλήσεις"
        subtitle="Ο AI βοηθός τηλεφωνεί στον πωλητή, του εξηγεί τις προτάσεις, δέχεται αλλαγές ποσότητας και φτιάχνει draft στο ERP μόνο μετά από ρητή φωνητική επιβεβαίωση." />

      <div className="reveal grid gap-6 lg:grid-cols-3">
        <Card title="Νέα κλήση" subtitle="Μόνο σε εγκεκριμένους αριθμούς, εργάσιμες ώρες.">
          <div className="flex flex-col gap-3">
            <Select label="Πωλητής" value={selected} onChange={setWho}
              options={(salesmen.data ?? []).map((s) => ({ value: String(s.PRSN), label: `${s.NAME} · ${fmtNum(pending.get(s.PRSN) ?? 0)} προτάσεις` }))} />
            <button className="btn btn-primary" onClick={dial} disabled={dialing || !selected}>
              {dialing ? "Κλήση…" : "📞 Κάλεσε τον πωλητή"}
            </button>
            {msg && (
              <p role="status" className="fade-in text-sm text-ink-2">
                <span aria-hidden style={{ color: msg.ok ? "var(--good)" : "var(--critical)" }}>{msg.ok ? "✓" : "!"}</span> {msg.text}
              </p>
            )}
            <ul className="mt-1 space-y-1.5 text-xs text-ink-muted">
              <li>• Ο βοηθός λέει από την αρχή ότι είναι AI.</li>
              <li>• Πριν από κάθε παραγγελία διαβάζει την ακριβή περίληψη και περιμένει «ναι, επιβεβαιώνω».</li>
              <li>• Μία επιβεβαίωση = ακριβώς ένα draft, ακόμη κι αν κοπεί η γραμμή.</li>
            </ul>
          </div>
        </Card>

        <div className="space-y-4 lg:col-span-2">
          {calls.data.length === 0 ? (
            <EmptyState title="Καμία κλήση ακόμη">
              Ξεκίνησε μια κλήση από αριστερά. Η κατάσταση, το transcript και το draft εμφανίζονται εδώ ζωντανά.
            </EmptyState>
          ) : calls.data.map((c) => <CallCard key={c.call_sid} c={c} name={c.salesman ? names.get(c.salesman) : undefined} />)}
        </div>
      </div>
    </>
  );
}

function CallCard({ c, name }: { c: Call; name?: string }) {
  const idx = stepIndex(c.status);
  const failed = c.status === "failed" || c.status === "cancelled";
  return (
    <Card lift title={<span className="flex items-center gap-2">{name ?? "Πωλητής"} <CallStatusBadge status={c.status} /></span>}
      subtitle={<span className="tnum">{time.format(new Date(c.started_at))}{c.ended_at ? ` – ${time.format(new Date(c.ended_at))}` : ""} · {c.call_sid}</span>}>
      <ol className="mb-4 flex flex-wrap items-center gap-1.5" aria-label="Πρόοδος κλήσης">
        {CALL_STEPS.map((s, i) => {
          const done = !failed && i <= idx;
          return (
            <li key={s.key} className="flex items-center gap-1.5">
              <span className="rounded-full px-2 py-0.5 text-xs transition-colors duration-300"
                style={{
                  background: done ? "var(--series-1-wash)" : "var(--surface-2)",
                  color: done ? "var(--ink)" : "var(--ink-muted)",
                  fontWeight: i === idx && isLive(c.status) ? 600 : 400,
                }}>{s.label}</span>
              {i < CALL_STEPS.length - 1 && <span aria-hidden className="text-ink-muted">›</span>}
            </li>
          );
        })}
      </ol>

      {c.transcript.length > 0 ? (
        <div className="max-h-72 space-y-2 overflow-y-auto pr-1">
          {c.transcript.map((t, i) => {
            const agent = t.role === "agent" || t.role === "assistant";
            return (
              <div key={i} className={`fade-in flex ${agent ? "justify-start" : "justify-end"}`}>
                <div className="max-w-[80%] rounded-2xl px-3 py-2 text-sm"
                  style={{ background: agent ? "var(--surface-2)" : "var(--series-1-wash)", color: "var(--ink)" }}>
                  <div className="mb-0.5 text-[11px] text-ink-muted">{agent ? "AI βοηθός" : name ?? "Πωλητής"} · {time.format(new Date(t.at))}</div>
                  {t.text}
                </div>
              </div>
            );
          })}
        </div>
      ) : <p className="text-sm text-ink-muted">Δεν υπάρχει ακόμη transcript.</p>}

      {(c.erp_draft_ids.length > 0 || c.suggestion_ids.length > 0) && (
        <div className="mt-4 flex flex-wrap gap-x-5 gap-y-1 border-t border-[var(--grid)] pt-3 text-xs text-ink-2">
          {c.erp_draft_ids.map((d) => <span key={d}><span aria-hidden style={{ color: "var(--good)" }}>✓</span> Draft <code className="font-semibold text-ink">{d}</code></span>)}
          {c.suggestion_ids.map((id) => <Link key={id} href={`/orders?open=${id}`} className="hover:text-ink">Πρόταση {id} →</Link>)}
        </div>
      )}
    </Card>
  );
}
