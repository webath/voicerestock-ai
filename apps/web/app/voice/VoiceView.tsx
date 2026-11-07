"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useToast } from "@/components/Toast";
import { CALL_STEPS, CallStatusBadge, isLive, stepIndex } from "@/components/CallStatus";
import { Card, EmptyState, ErrorBox, Loading, PageHeader, Select } from "@/components/ui";
import { ApiError, apiPost, useApi, VOICE_TOKEN, VOICE_URL, type Call, type Salesman, type Suggestion } from "@/lib/api";
import { fmtNum } from "@/lib/format";
import { byPriority, priorityOf } from "@/lib/priority";

const time = new Intl.DateTimeFormat("el-GR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
const isSim = (c: Call) => c.call_sid.startsWith("SIM-");
const PRIORITY_LABEL: Record<string, string> = { critical: "κρίσιμος", high: "επείγων", lost: "πιθανή απώλεια", medium: "μέτριος", low: "χαμηλός" };
const TUNNEL_CMD = "VPS_KEY=~/.ssh/id_ed25519 apps/voice/deploy/tunnel.sh";

interface VoiceHealth { ok: boolean; active_calls: string[]; quiet_hours: boolean; salesmen_with_phone: number[] }

/** Ζει ο voice agent (VPS, μέσω tunnel); Ρωτάμε το /voice/health κάθε 5″ — χωρίς αυτό η live κλήση δεν φεύγει. */
function useVoiceHealth() {
  const [h, setH] = useState<VoiceHealth | null | "down">(null);
  useEffect(() => {
    let alive = true;
    const check = () => fetch(`${VOICE_URL}/voice/health`, { signal: AbortSignal.timeout(3000) })
      .then((r) => r.json()).then((j: VoiceHealth) => alive && setH(j)).catch(() => alive && setH("down"));
    check();
    const id = setInterval(check, 5000);
    return () => { alive = false; clearInterval(id); };
  }, []);
  return h;
}

/** Φωνή του browser (el-GR) για την προσομοίωση: η VORA με την πρώτη ελληνική φωνή, ο πωλητής με δεύτερη ή πιο βαθιά. */
function speak(text: string, agent: boolean) {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
  const greek = window.speechSynthesis.getVoices().filter((v) => v.lang.toLowerCase().startsWith("el"));
  const u = new SpeechSynthesisUtterance(text.replace(/«|»/g, ""));
  u.lang = "el-GR";
  u.rate = 1.08;
  const v = agent ? greek[0] : greek[1] ?? greek[0];
  if (v) u.voice = v;
  if (!agent && greek.length < 2) u.pitch = 0.7;
  window.speechSynthesis.speak(u);
}

export function VoiceView() {
  const calls = useApi<Call[]>("/api/calls");
  const salesmen = useApi<Salesman[]>("/api/salesmen");
  const sugs = useApi<Suggestion[]>("/api/suggestions");
  const params = useSearchParams();
  const toast = useToast();
  const [who, setWho] = useState(params.get("salesman") ?? "");
  const [dialing, setDialing] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [simulating, setSimulating] = useState(false);
  const health = useVoiceHealth();
  const [simMsg, setSimMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [sound, setSound] = useState(true);
  const spoken = useRef<Set<string> | null>(null);

  // Όσο «μιλάει» μια κλήση (ή μόλις μίλησε μια προσομοίωση), ανανέωση κάθε 0,7″ αντί για 3″.
  const latest = useRef<{ data?: Call[] | null; sim: boolean }>({ sim: false });
  useEffect(() => { latest.current = { data: calls.data, sim: simulating }; });
  const { reload } = calls;
  useEffect(() => {
    let t: ReturnType<typeof setTimeout>;
    const tick = () => {
      reload();
      const now = Date.now(), { data, sim } = latest.current;
      const fast = sim || (data ?? []).some((c) => isLive(c.status)
        || (isSim(c) && now - Date.parse(c.transcript.at(-1)?.at ?? c.started_at) < 15_000));
      t = setTimeout(tick, fast ? 700 : 3000);
    };
    t = setTimeout(tick, 3000);
    return () => clearTimeout(t);
  }, [reload]);

  // Νέες ατάκες προσομοίωσης → φωνή. Ό,τι υπήρχε ήδη όταν άνοιξε η σελίδα δεν ξαναλέγεται.
  useEffect(() => {
    if (!calls.data) return;
    const first = spoken.current === null;
    const seen = (spoken.current ??= new Set());
    for (const c of [...calls.data].reverse()) {
      c.transcript.forEach((t, i) => {
        const k = `${c.call_sid}#${i}`;
        if (seen.has(k)) return;
        seen.add(k);
        if (!first && sound && isSim(c)) speak(t.text, t.role === "agent" || t.role === "assistant");
      });
    }
  }, [calls.data, sound]);
  useEffect(() => () => { if (typeof window !== "undefined") window.speechSynthesis?.cancel(); }, []);

  if (calls.error) return <ErrorBox message={calls.error} />;
  if (!calls.data) return <Loading />;

  const names = new Map((salesmen.data ?? []).map((s) => [s.PRSN, s.NAME]));
  const pending = new Map<number, number>();
  for (const s of sugs.data ?? []) if (s.status !== "draft_created" && s.status !== "cancelled") pending.set(s.SALESMAN, (pending.get(s.SALESMAN) ?? 0) + 1);
  // Προεπιλογή: πωλητής με τηλέφωνο, αλλιώς ο 105 του demo, αλλιώς ο πρώτος.
  const list = salesmen.data ?? [];
  const fallback = list.find((s) => s.phone) ?? list.find((s) => s.PRSN === 105) ?? list[0];
  const selected = who || String(fallback?.PRSN ?? "");
  // Από ποιον πελάτη θα ξεκινήσει η κλήση: ίδια σειρά με τον voice agent (vr_core.priority_sort_key)
  const next = (sugs.data ?? []).filter((s) => s.SALESMAN === Number(selected) && (s.status === "proposed" || s.status === "modified"))
    .sort(byPriority)[0];
  const online = health !== null && health !== "down" && health.ok;
  const hasPhone = online && health.salesmen_with_phone.includes(Number(selected));

  async function dial() {
    setDialing(true); setMsg(null);
    try {
      await apiPost("/voice/calls", { salesman: Number(selected) }, VOICE_URL, VOICE_TOKEN ? { "X-Voice-Token": VOICE_TOKEN } : {});
      setMsg({ ok: true, text: `Το κινητό χτυπά σε λίγα δευτερόλεπτα${next ? ` — η VORA ξεκινά από τον πελάτη ${next.CUSTOMER_NAME}` : ""}. Η κλήση εμφανίζεται live δεξιά.` });
      toast({ kind: "success", title: "Η κλήση ξεκίνησε", text: `Ο AI βοηθός καλεί τον/την ${names.get(Number(selected)) ?? selected}.` });
      calls.reload();
    } catch (e) {
      setMsg({ ok: false, text: e instanceof TypeError
        ? `Ο voice agent δεν απαντά στο ${VOICE_URL}. Άνοιξε το tunnel: ${TUNNEL_CMD}`
        : (e as Error).message });
      toast({ kind: "error", title: "Η κλήση δεν ξεκίνησε", text: e instanceof TypeError ? `Ο voice agent δεν απαντά (${VOICE_URL}).` : (e as Error).message });
    } finally { setDialing(false); }
  }

  async function simulate() {
    setSimulating(true); setSimMsg(null);
    window.speechSynthesis?.cancel();
    try {
      const r = await apiPost<{ customer: string; priority: string }>("/api/calls/simulate", { salesman: Number(selected) });
      setSimMsg({ ok: true, text: `Η VORA καλεί για τον πελάτη ${r.customer} (${PRIORITY_LABEL[r.priority] ?? r.priority}).` });
      calls.reload();
    } catch (e) {
      const text = e instanceof ApiError && e.code === "no_suggestion"
        ? "Ο πωλητής δεν έχει άλλη ανοιχτή πρόταση — διάλεξε άλλον πωλητή."
        : e instanceof ApiError && e.code === "sim_running" ? "Τρέχει ήδη μια προσομοίωση." : (e as Error).message;
      setSimMsg({ ok: false, text });
      toast({ kind: "error", title: "Η προσομοίωση δεν ξεκίνησε", text });
    } finally { setTimeout(() => setSimulating(false), 4000); }
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
            <VoiceStatus health={health} hasPhone={hasPhone} />
            {next && (
              <p className="text-xs text-ink-2">
                Η VORA θα ξεκινήσει από τον πιο επείγοντα: <strong className="text-ink">{next.CUSTOMER_NAME}</strong>{" "}
                ({PRIORITY_LABEL[priorityOf(next).priority] ?? priorityOf(next).priority})
              </p>
            )}
            <button className="btn btn-primary" onClick={dial} disabled={dialing || !selected}>
              {dialing ? <><span className="ai-dots" aria-hidden><i /><i /><i /></span> Καλεί…</> : "📞 Live κλήση στο κινητό"}
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

            <div className="mt-2 border-t border-[var(--grid)] pt-4">
              <div className="mb-1 text-sm font-semibold text-ink">Plan B · χωρίς τηλέφωνο</div>
              <p className="mb-3 text-xs text-ink-2">
                Αν πέσει το δίκτυο ή το τηλέφωνο: η ίδια κλήση παίζεται στην οθόνη, με φωνή από τον browser. Οι ατάκες του
                πωλητή είναι έτοιμες· η αλλαγή ποσότητας και το draft περνούν κανονικά από το App API στο ERP.
              </p>
              <button className="btn btn-ghost w-full" onClick={simulate} disabled={simulating || !selected}>
                {simulating ? <><span className="ai-dots" aria-hidden><i /><i /><i /></span> Καλεί…</> : "▶ Προσομοίωση κλήσης"}
              </button>
              <label className="mt-2 flex cursor-pointer items-center gap-2 text-xs text-ink-2">
                <input type="checkbox" checked={sound} onChange={(e) => { setSound(e.target.checked); if (!e.target.checked) window.speechSynthesis?.cancel(); }} />
                Φωνή (ελληνικά, από τον browser)
              </label>
              {simMsg && (
                <p role="status" className="fade-in mt-2 text-sm text-ink-2">
                  <span aria-hidden style={{ color: simMsg.ok ? "var(--good)" : "var(--critical)" }}>{simMsg.ok ? "✓" : "!"}</span> {simMsg.text}
                </p>
              )}
            </div>
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

function VoiceStatus({ health, hasPhone }: { health: VoiceHealth | null | "down"; hasPhone: boolean }) {
  const [color, text, hint] =
    health === null ? ["var(--ink-muted)", "Έλεγχος voice agent…", null]
    : health === "down" || !health.ok ? ["var(--critical)", "Ο voice agent δεν απαντά", <>Άνοιξε το tunnel σε ένα terminal: <code className="break-all">{TUNNEL_CMD}</code></>]
    : health.quiet_hours ? ["var(--warning)", "Voice agent online · ώρες ησυχίας", "Οι κλήσεις δεν φεύγουν τώρα (QUIET_HOURS στο VPS)."]
    : !hasPhone ? ["var(--warning)", "Voice agent online", "Αυτός ο πωλητής δεν έχει κινητό στο VPS — διάλεξε τον Στέλιο Παπαγεωργίου."]
    : health.active_calls.length ? ["var(--series-1)", "Voice agent online · κλήση σε εξέλιξη", null]
    : ["var(--good)", "Voice agent online · έτοιμος να καλέσει", null];
  return (
    <div role="status" className="rounded-xl border border-line bg-surface-2 px-3 py-2 text-xs">
      <div className="flex items-center gap-2 font-semibold text-ink">
        <span aria-hidden className={health && health !== "down" && health.ok ? "pulse-dot" : ""} style={{ color }}>●</span>{text}
      </div>
      {hint && <div className="mt-1 text-ink-2">{hint}</div>}
    </div>
  );
}

function CallCard({ c, name }: { c: Call; name?: string }) {
  const idx = stepIndex(c.status);
  const failed = c.status === "failed" || c.status === "cancelled";
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => { box.current?.scrollTo({ top: box.current.scrollHeight, behavior: "smooth" }); }, [c.transcript.length]);
  return (
    <Card lift title={<span className="flex items-center gap-2">{name ?? "Πωλητής"} <CallStatusBadge status={c.status} />
      {isSim(c) && <span className="rounded-full border border-line px-2 py-0.5 text-xs font-normal text-ink-muted">προσομοίωση</span>}</span>}
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
        <div ref={box} className="max-h-96 space-y-2 overflow-y-auto pr-1">
          {c.transcript.map((t, i) => {
            const agent = t.role === "agent" || t.role === "assistant";
            return (
              <div key={i} className={`fade-in flex ${agent ? "justify-start" : "justify-end"}`}>
                <div className="max-w-[80%] rounded-2xl px-3 py-2 text-sm"
                  style={{ background: agent ? "var(--surface-2)" : "var(--series-1-wash)", color: "var(--ink)" }}>
                  <div className="mb-0.5 text-[11px] text-ink-muted">{agent ? "VORA · AI βοηθός" : name ?? "Πωλητής"} · {time.format(new Date(t.at))}</div>
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
