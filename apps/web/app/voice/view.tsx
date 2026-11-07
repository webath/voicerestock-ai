"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useSalesman } from "@/components/salesman";
import { Badge, Card, CallStatusBadge, Empty, ErrorBox, PageHeader, Skeleton, btn, input } from "@/components/ui";
import { ApiError, useApi, voice } from "@/lib/api";
import { CALL_STATUS, fmtTime } from "@/lib/format";
import type { Call, CallStatus, VoiceHealth } from "@/lib/types";

const STEPS: { key: CallStatus[]; label: string }[] = [
  { key: ["queued", "dialing"], label: "Κλήση" },
  { key: ["connected", "greeted"], label: "Απάντησε" },
  { key: ["discussing"], label: "Συζήτηση" },
  { key: ["confirming"], label: "Επιβεβαίωση" },
  { key: ["posting_draft", "draft_created"], label: "Draft στο ERP" },
];

function Stepper({ call }: { call: Call }) {
  // Πόσο μακριά έφτασε η κλήση (τα τελικά status δεν «γυρνάνε πίσω» το stepper).
  const order: CallStatus[] = ["queued", "dialing", "connected", "greeted", "discussing", "confirming", "posting_draft", "draft_created"];
  let reached = order.indexOf(call.status);
  if (reached < 0) {
    // ended / failed / cancelled: πόσο προχώρησε, από το transcript
    reached = order.indexOf(call.transcript.some((t) => t.role === "user") ? "discussing" : call.transcript.length ? "greeted" : "dialing");
  }
  if (call.erp_draft_ids.length) reached = order.length - 1;
  return (
    <ol className="flex flex-wrap items-center gap-1.5 text-xs" aria-label="Πρόοδος κλήσης">
      {STEPS.map((s, i) => {
        const idx = Math.max(...s.key.map((k) => order.indexOf(k)));
        const first = Math.min(...s.key.map((k) => order.indexOf(k)));
        const done = reached >= idx;
        const current = !done && reached >= first;
        return (
          <li key={s.label} className="flex items-center gap-1.5">
            <span className={`rounded-full px-2 py-0.5 ring-1 ring-inset ring-line ${done ? "bg-tint-good text-good-ink" : current ? "bg-tint-info text-ink" : "text-muted"}`}>
              {done ? "✓ " : ""}{s.label}
            </span>
            {i < STEPS.length - 1 && <span aria-hidden className="text-muted">›</span>}
          </li>
        );
      })}
    </ol>
  );
}

function Transcript({ call }: { call: Call }) {
  const end = useRef<HTMLDivElement>(null);
  const live = CALL_STATUS[call.status]?.live;
  useEffect(() => {
    if (live) end.current?.scrollIntoView({ block: "nearest" });
  }, [call.transcript.length, live]);
  if (!call.transcript.length) return <p className="px-4 py-6 text-center text-sm text-muted">Δεν έχει ειπωθεί τίποτα ακόμα.</p>;
  return (
    <div className="max-h-96 space-y-2 overflow-y-auto px-4 py-3">
      {call.transcript.map((t, i) => (
        <div key={i} className={`flex ${t.role === "agent" ? "justify-start" : "justify-end"}`}>
          <div className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm ${t.role === "agent" ? "rounded-tl-sm bg-surface-2 text-ink" : "rounded-tr-sm bg-ink text-page"}`}>
            <div className={`mb-0.5 text-[11px] ${t.role === "agent" ? "text-muted" : "opacity-70"}`}>
              {t.role === "agent" ? "Ψηφιακή βοηθός" : "Πωλητής"} · {fmtTime(t.at)}
            </div>
            {t.text}
          </div>
        </div>
      ))}
      <div ref={end} />
    </div>
  );
}

export default function VoiceView() {
  const { salesman, salesmen, name } = useSalesman();
  const health = useApi<VoiceHealth>("/health", { refreshMs: 5_000, client: voice });
  const calls = useApi<Call[]>("/calls", { refreshMs: 2_000 });
  const [target, setTarget] = useState<number | "">("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string }>();
  const [open, setOpen] = useState<string>();

  const callable = salesmen.filter((s) => s.phone);
  const chosen = target === "" ? (salesman != null && callable.some((s) => s.PRSN === salesman) ? salesman : callable[0]?.PRSN) : target;
  const list = (calls.data ?? []).filter((c) => salesman == null || c.salesman == null || c.salesman === salesman);
  const expanded = open ?? list[0]?.call_sid;

  const blocked = !health.data
    ? "Ο voice agent δεν απαντά (τρέχει το tunnel;)"
    : health.data.quiet_hours
      ? "Ώρες ησυχίας: δεν γίνονται κλήσεις."
      : health.data.active_calls.length
        ? "Υπάρχει ήδη κλήση σε εξέλιξη."
        : chosen == null
          ? "Κανένας πωλητής με καταχωρισμένο τηλέφωνο."
          : null;

  const call = async () => {
    if (chosen == null) return;
    setBusy(true);
    setMsg(undefined);
    try {
      const r = await voice<{ call_sid: string; suggestions: number }>("/calls", { method: "POST", json: { salesman: chosen } });
      setMsg({ ok: true, text: `Καλείται ο/η ${name(chosen)} · ${r.suggestions} προτάσεις προς συζήτηση.` });
      setOpen(r.call_sid);
      calls.reload();
      health.reload();
    } catch (e) {
      setMsg({ ok: false, text: e instanceof ApiError ? e.message : String(e) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PageHeader
        title="Κλήσεις"
        subtitle="Η ψηφιακή βοηθός καλεί τον πωλητή, εξηγεί τις προτάσεις και δημιουργεί draft στο ERP μόνο μετά από ρητό «ναι»."
      />

      <Card title="Κάλεσε τον πωλητή" className="mb-4">
        <div className="flex flex-wrap items-center gap-3 p-4">
          <select className={input} value={chosen ?? ""} onChange={(e) => setTarget(e.target.value ? Number(e.target.value) : "")} aria-label="Πωλητής">
            {callable.length === 0 && <option value="">—</option>}
            {callable.map((s) => (
              <option key={s.PRSN} value={s.PRSN}>{s.NAME} · {s.phone}</option>
            ))}
          </select>
          <button className={btn.primary} onClick={call} disabled={busy || Boolean(blocked)}>
            <span aria-hidden>☏</span> {busy ? "Κλήση…" : "Κάλεσε τώρα"}
          </button>
          <span className="text-xs text-muted">
            {blocked ?? "Ο αριθμός πρέπει να είναι στο allowlist του voice agent."}
          </span>
        </div>
        {msg && (
          <div className="px-4 pb-4">
            {msg.ok ? (
              <div className="rounded-lg bg-tint-good px-4 py-2.5 text-sm text-good-ink ring-1 ring-line">✓ {msg.text}</div>
            ) : (
              <ErrorBox error={{ message: msg.text }} />
            )}
          </div>
        )}
      </Card>

      {calls.error && <div className="mb-4"><ErrorBox error={calls.error} onRetry={calls.reload} /></div>}

      {!calls.data ? (
        <Skeleton className="h-64" />
      ) : list.length === 0 ? (
        <div className="rounded-xl bg-surface ring-1 ring-line"><Empty>Καμία κλήση ακόμα.</Empty></div>
      ) : (
        <div className="space-y-3">
          {list.map((c) => {
            const isOpen = expanded === c.call_sid;
            const live = CALL_STATUS[c.status]?.live;
            return (
              <article key={c.call_sid} className="rounded-xl bg-surface ring-1 ring-line">
                <button
                  className="flex w-full flex-wrap items-center justify-between gap-3 px-4 py-3 text-left"
                  onClick={() => setOpen(isOpen ? "" : c.call_sid)}
                  aria-expanded={isOpen}
                >
                  <span className="flex flex-wrap items-center gap-2">
                    {live && <span aria-hidden className="size-2 animate-pulse rounded-full bg-critical" />}
                    <span className="text-sm font-semibold text-ink">{name(c.salesman) || "Άγνωστος καλών"}</span>
                    <CallStatusBadge status={c.status} />
                    {c.erp_draft_ids.map((d) => <Badge key={d} tone="good">{d}</Badge>)}
                  </span>
                  <span className="text-xs text-muted">
                    {fmtTime(c.started_at)}{c.ended_at ? ` – ${fmtTime(c.ended_at)}` : " · σε εξέλιξη"} · {c.call_sid}
                  </span>
                </button>
                {isOpen && (
                  <div className="border-t border-line">
                    <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-3">
                      <Stepper call={c} />
                      {c.suggestion_ids.length > 0 && (
                        <span className="text-xs text-ink-2">
                          Προτάσεις:{" "}
                          {c.suggestion_ids.map((id, i) => (
                            <span key={id}>{i > 0 && ", "}<Link className="font-medium text-series hover:underline" href={`/orders#${id}`}>{id}</Link></span>
                          ))}
                        </span>
                      )}
                    </div>
                    <Transcript call={c} />
                  </div>
                )}
              </article>
            );
          })}
        </div>
      )}
    </>
  );
}
