"use client";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { API_URL, apiGet, type Salesman } from "@/lib/api";
import { Markdown } from "./Markdown";

interface Step { name: string; label: string; detail: string }
interface Msg { role: "user" | "assistant"; content: string; steps?: Step[]; error?: string; streaming?: boolean }

const EXAMPLES = [
  "Ποιοι πελάτες μου ξεμένουν από νερά τις επόμενες 3 μέρες;",
  "Με ποιους πελάτες να ξεκινήσω σήμερα;",
  "Γιατί προτείνετε αυτή την παραγγελία στο Mini Market Οικονομικό;",
  "Πόσο ακριβές είναι το μοντέλο;",
];

function describe(input: Record<string, unknown>): string {
  const parts: string[] = [];
  if (input.category) parts.push(String(input.category));
  if (input.item_query) parts.push(`«${input.item_query}»`);
  if (input.area) parts.push(String(input.area));
  if (input.customer_type) parts.push(String(input.customer_type));
  if (input.days) parts.push(`${input.days} μέρες`);
  if (input.query) parts.push(`«${input.query}»`);
  if (input.trdr) parts.push(`#${input.trdr}`);
  return parts.join(" · ");
}

/** «Ρώτα το AI»: πάνελ σε κάθε σελίδα. Ο βοηθός ψάχνει μόνος του στα δεδομένα (εργαλεία μόνο ανάγνωσης) και απαντά live. */
export function AssistantPanel() {
  const [open, setOpen] = useState(false);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [salesman, setSalesman] = useState("105");
  const [salesmen, setSalesmen] = useState<Salesman[]>([]);
  const scroller = useRef<HTMLDivElement>(null);
  const box = useRef<HTMLTextAreaElement>(null);
  const path = usePathname();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "j") { e.preventDefault(); setOpen((o) => !o); }
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  useEffect(() => { if (open) { box.current?.focus(); if (!salesmen.length) apiGet<Salesman[]>("/api/salesmen").then(setSalesmen).catch(() => {}); } }, [open, salesmen.length]);
  useEffect(() => { scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" }); }, [msgs]);

  // Στη σελίδα πελάτη, «αυτόν τον πελάτη» = ο πελάτης της σελίδας.
  const pageHint = path.startsWith("/customers/") ? ` (βλέπω τον πελάτη #${path.split("/")[2]})` : "";

  async function ask(q: string) {
    if (!q.trim() || busy) return;
    const history = [...msgs.filter((m) => !m.error).map((m) => ({ role: m.role, content: m.content })), { role: "user" as const, content: q + pageHint }];
    setMsgs((m) => [...m, { role: "user", content: q }, { role: "assistant", content: "", steps: [], streaming: true }]);
    setInput(""); setBusy(true);
    const patch = (f: (m: Msg) => Msg) => setMsgs((ms) => [...ms.slice(0, -1), f(ms[ms.length - 1])]);
    try {
      const r = await fetch(`${API_URL}/api/assistant`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: history, salesman: salesman ? Number(salesman) : null }),
      });
      if (!r.ok || !r.body) throw new Error(`HTTP ${r.status}`);
      const reader = r.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let i;
        while ((i = buf.indexOf("\n\n")) >= 0) {
          const chunk = buf.slice(0, i); buf = buf.slice(i + 2);
          if (!chunk.startsWith("data: ")) continue;
          const ev = JSON.parse(chunk.slice(6));
          if (ev.type === "text") patch((m) => ({ ...m, content: m.content + ev.delta }));
          else if (ev.type === "tool") patch((m) => ({ ...m, steps: [...(m.steps ?? []), { name: ev.name, label: ev.label, detail: describe(ev.input ?? {}) }] }));
          else if (ev.type === "error") patch((m) => ({ ...m, error: ev.message }));
        }
      }
    } catch (e) {
      patch((m) => ({ ...m, error: e instanceof TypeError ? "Δεν απαντά το App API." : (e as Error).message }));
    } finally {
      patch((m) => ({ ...m, streaming: false }));
      setBusy(false);
    }
  }

  return (
    <>
      <button type="button" onClick={() => setOpen(true)} aria-label="Ρώτα το AI (⌘J)"
        className={`ai-fab fixed bottom-5 right-5 z-40 inline-flex items-center gap-2 rounded-full px-4 py-3 text-sm font-semibold text-white ${open ? "pointer-events-none opacity-0" : ""}`}>
        <Sparkle /> Ρώτα το AI
      </button>

      <aside aria-label="AI βοηθός" aria-hidden={!open} inert={!open}
        className={`ai-panel fixed inset-y-0 right-0 z-50 flex w-full max-w-[440px] flex-col ${open ? "ai-panel-open" : ""}`}>
        <header className="flex items-center gap-3 border-b border-[var(--grid)] px-4 py-3">
          <span className="ai-orb" aria-hidden><Sparkle /></span>
          <div className="min-w-0 flex-1">
            <div className="text-sm font-semibold text-ink">VORA · AI βοηθός πωλήσεων</div>
            <div className="text-xs text-ink-muted">Ψάχνει μόνο στα δεδομένα του συστήματος · δεν αλλάζει παραγγελίες</div>
          </div>
          <button type="button" className="btn btn-ghost btn-sm !h-8 !w-8 !p-0" onClick={() => setOpen(false)} aria-label="Κλείσιμο">✕</button>
        </header>
        <div className="flex items-center gap-2 border-b border-[var(--grid)] px-4 py-2 text-xs text-ink-2">
          <span>Μιλάω ως</span>
          <select className="field !h-8 !rounded-lg !px-2 !text-xs" value={salesman} onChange={(e) => setSalesman(e.target.value)} aria-label="Πωλητής">
            <option value="">Διευθυντής (όλοι)</option>
            {salesmen.map((s) => <option key={s.PRSN} value={s.PRSN}>{s.NAME}</option>)}
          </select>
          {msgs.length > 0 && <button type="button" className="ml-auto text-ink-muted hover:text-ink" onClick={() => setMsgs([])}>Νέα συζήτηση</button>}
        </div>

        <div ref={scroller} className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
          {msgs.length === 0 && (
            <div className="fade-in">
              <p className="text-sm text-ink-2">Ρώτα ό,τι θες για τους πελάτες, τις προβλέψεις και τις παραγγελίες. Για παράδειγμα:</p>
              <div className="mt-3 flex flex-col gap-2">
                {EXAMPLES.map((e) => (
                  <button key={e} type="button" onClick={() => ask(e)} className="card lift !rounded-xl px-3 py-2 text-left text-sm text-ink">{e}</button>
                ))}
              </div>
            </div>
          )}
          {msgs.map((m, i) => m.role === "user" ? (
            <div key={i} className="fade-in flex justify-end">
              <div className="max-w-[85%] rounded-2xl rounded-br-md px-3.5 py-2 text-sm text-white" style={{ background: "var(--series-1)" }}>{m.content}</div>
            </div>
          ) : (
            <div key={i} className="fade-in">
              {(m.steps ?? []).length > 0 && (
                <ol className="mb-2 space-y-1">
                  {m.steps!.map((s, j) => (
                    <li key={j} className="ai-step flex items-center gap-2 text-xs text-ink-2" style={{ animationDelay: `${j * 60}ms` }}>
                      <span aria-hidden className="flex h-4 w-4 items-center justify-center rounded-full text-[10px]" style={{ background: "var(--series-1-wash)", color: "var(--series-1)" }}>✓</span>
                      <span className="font-medium text-ink">{s.label}</span>{s.detail && <span className="text-ink-muted">· {s.detail}</span>}
                    </li>
                  ))}
                </ol>
              )}
              {m.streaming && !m.content && !m.error && (
                <div className="flex items-center gap-2 text-xs text-ink-muted"><span className="ai-dots" aria-hidden><i /><i /><i /></span>
                  {(m.steps ?? []).length ? "Γράφω την απάντηση…" : "Σκέφτομαι…"}</div>
              )}
              {m.content && <div className={m.streaming ? "ai-caret" : ""}><Markdown text={m.content} /></div>}
              {m.error && <p role="alert" className="text-sm text-ink"><span aria-hidden style={{ color: "var(--critical)" }}>!</span> {m.error}</p>}
            </div>
          ))}
        </div>

        <form className="border-t border-[var(--grid)] p-3" onSubmit={(e) => { e.preventDefault(); ask(input); }}>
          <div className="flex items-end gap-2">
            <textarea ref={box} rows={1} value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ρώτα κάτι… (Enter για αποστολή)"
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(input); } }}
              className="field max-h-32 min-h-[40px] flex-1 resize-none !py-2.5" aria-label="Ερώτηση προς τον AI βοηθό" />
            <button type="submit" className="btn btn-primary !h-10" disabled={busy || !input.trim()} aria-label="Αποστολή">↑</button>
          </div>
          <p className="mt-1.5 text-[11px] text-ink-muted">Claude · απαντά από προβλέψεις & προτάσεις του συστήματος. ⌘J για άνοιγμα/κλείσιμο.</p>
        </form>
      </aside>
      {open && <div className="fixed inset-0 z-40 bg-black/20 sm:bg-transparent" onClick={() => setOpen(false)} aria-hidden />}
    </>
  );
}

export function Sparkle({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden fill="currentColor">
      <path d="M12 2.5c.4 3.9 1.9 6.4 4.3 7.6 1.2.6 2.6.9 4.2 1.1v1.6c-1.6.2-3 .5-4.2 1.1-2.4 1.2-3.9 3.7-4.3 7.6h-1.6c-.4-3.9-1.9-6.4-4.3-7.6-1.2-.6-2.6-.9-4.2-1.1v-1.6c1.6-.2 3-.5 4.2-1.1 2.4-1.2 3.9-3.7 4.3-7.6H12z" />
    </svg>
  );
}
