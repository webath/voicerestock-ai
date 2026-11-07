"use client";
import { useEffect, useState } from "react";
import { apiPost, useApi, type Salesman } from "@/lib/api";
import { Sparkle } from "./AssistantPanel";
import { Markdown } from "./Markdown";
import { useToast } from "./Toast";
import { SkeletonLines } from "./ui";

/** Κείμενο που «γράφεται» μπροστά σου (σβήνει με reduced motion). Νέο κείμενο → νέο key → ξεκινά από την αρχή. */
export function Typewriter({ text, speed = 14 }: { text: string; speed?: number }) {
  const reduce = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  const [n, setN] = useState(reduce ? text.length : 0);
  useEffect(() => {
    if (n >= text.length) return;
    const id = setTimeout(() => setN((x) => Math.min(text.length, x + 3)), speed);
    return () => clearTimeout(id);
  }, [n, text.length, speed]);
  return <div className={n < text.length ? "ai-caret" : ""}><Markdown text={text.slice(0, n)} /></div>;
}

export function AiBadge({ source }: { source?: string }) {
  return source === "llm"
    ? <span className="ai-badge"><Sparkle size={10} /> AI</span>
    : <span className="rounded-full border border-line px-2 py-0.5 text-[11px] text-ink-muted">αυτόματη περίληψη</span>;
}

/** Πρωινό briefing ανά πωλητή (Επισκόπηση). */
export function Briefing({ salesmen }: { salesmen: Salesman[] }) {
  const [who, setWho] = useState("105");
  const b = useApi<{ text: string; source: string }>(`/api/briefing?salesman=${who}`);
  return (
    <section className="card ai-shine min-w-0 p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="ai-orb !h-7 !w-7" aria-hidden><Sparkle size={13} /></span>
          <h2 className="text-base font-semibold text-ink">Πρωινό briefing</h2>
          {b.data && !b.loading && <AiBadge source={b.data.source} />}
        </div>
        <select className="field !h-8 !rounded-lg !px-2 !text-xs" value={who} onChange={(e) => setWho(e.target.value)} aria-label="Πωλητής για το briefing">
          {salesmen.map((s) => <option key={s.PRSN} value={s.PRSN}>{s.NAME}</option>)}
        </select>
      </div>
      <div className="mt-3 min-h-[120px]">
        {b.error ? <p className="text-sm text-ink-2">Το briefing δεν είναι διαθέσιμο.</p>
          : b.data && !b.loading ? <Typewriter key={b.data.text} text={b.data.text} />
          : <><SkeletonLines lines={4} /><p className="mt-2 text-xs text-ink-muted">Το AI διαβάζει το χαρτοφυλάκιο του πωλητή…</p></>}
      </div>
    </section>
  );
}

/** Μήνυμα προς τον πελάτη (SMS / email) από την πρόταση — ο πωλητής το ελέγχει και το στέλνει ο ίδιος. */
export function CustomerMessage({ suggestionId }: { suggestionId: string }) {
  const toast = useToast();
  const [channel, setChannel] = useState<"sms" | "email" | null>(null);
  const [res, setRes] = useState<{ text: string; source: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function make(ch: "sms" | "email") {
    setChannel(ch); setBusy(true); setRes(null);
    try { setRes(await apiPost(`/api/suggestions/${suggestionId}/customer-message`, { channel: ch })); }
    catch (e) { toast({ kind: "error", title: "Δεν γράφτηκε μήνυμα", text: (e as Error).message }); setChannel(null); }
    finally { setBusy(false); }
  }
  async function copy() {
    if (!res) return;
    try { await navigator.clipboard.writeText(res.text); toast({ kind: "success", title: "Αντιγράφηκε", text: "Επικόλλησέ το σε SMS / email προς τον πελάτη." }); }
    catch { toast({ kind: "error", title: "Η αντιγραφή απέτυχε" }); }
  }

  return (
    <div className="mt-4 border-t border-[var(--grid)] pt-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-medium text-ink-2">Μήνυμα προς τον πελάτη</span>
        <button type="button" className="btn btn-ghost btn-sm" disabled={busy} onClick={() => make("sms")}><Sparkle size={11} /> SMS</button>
        <button type="button" className="btn btn-ghost btn-sm" disabled={busy} onClick={() => make("email")}><Sparkle size={11} /> Email</button>
      </div>
      {channel && (
        <div className="fade-in mt-3 rounded-xl bg-surface-2 p-3">
          {busy || !res ? <><SkeletonLines lines={3} /><p className="mt-2 text-xs text-ink-muted">Το AI γράφει {channel === "sms" ? "SMS" : "email"}…</p></>
            : (
              <>
                <div className="whitespace-pre-line text-sm text-ink">{res.text}</div>
                <div className="mt-3 flex items-center justify-between gap-2">
                  <AiBadge source={res.source} />
                  <button type="button" className="btn btn-primary btn-sm" onClick={copy}>Αντιγραφή</button>
                </div>
              </>
            )}
        </div>
      )}
    </div>
  );
}
