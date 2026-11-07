"use client";
import Link from "next/link";
import { useState } from "react";
import { Card, ErrorBox, Loading, PageHeader, StatTile } from "@/components/ui";
import { useToast } from "@/components/Toast";
import { ApiError, apiPost, useApi, usePolling, type AgentRun, type AgentState, type AgentStep } from "@/lib/api";
import { fmtEur, fmtNum } from "@/lib/format";
import { OperationsSummary } from "@/components/OperationsSummary";

// Owner: Δημήτρης. Δεδομένα: GET /api/agent (poll), POST /api/agent/run. Ο agent: services/forecast/src/forecast/agent.py.

const TRIGGER: Record<string, string> = { manual: "χειροκίνητα", schedule: "προγραμματισμένα", startup: "στην εκκίνηση", test: "δοκιμή" };

function when(iso?: string | null) {
  if (!iso) return "–";
  const d = new Date(iso);
  return `${d.toLocaleTimeString("el-GR", { hour: "2-digit", minute: "2-digit" })} · ${d.getDate()}/${d.getMonth() + 1}`;
}
function seconds(run: AgentRun) {
  if (!run.finished_at) return null;
  return Math.max(0, (Date.parse(run.finished_at) - Date.parse(run.started_at)) / 1000);
}
const n = (v: unknown) => (typeof v === "number" ? v : undefined);

export default function AgentPage() {
  const st = useApi<AgentState>("/api/agent");
  const toast = useToast();
  const [starting, setStarting] = useState(false);
  const running = !!st.data?.running || starting;
  usePolling(st.reload, running ? 350 : 5000);

  async function start() {
    setStarting(true);
    try {
      await apiPost("/api/agent/run");
      st.reload();
    } catch (e) {
      toast({ kind: "error", title: e instanceof ApiError && e.status === 409 ? "Ο agent τρέχει ήδη" : "Δεν ξεκίνησε", text: (e as Error).message });
    } finally {
      setTimeout(() => setStarting(false), 600);
    }
  }

  if (st.error) return <ErrorBox message={st.error} />;
  if (!st.data) return <Loading />;
  const run = st.data.current ?? st.data.last;
  // όσο τρέχει, οι κάρτες κρατούν τα νούμερα της προηγούμενης εκτέλεσης μέχρι να έρθουν τα νέα
  const m = (k: string) => run?.steps[k]?.metrics ?? st.data!.last?.steps?.[k]?.metrics ?? {};
  const sum = m("orders"), fetchM = m("fetch"), self = m("selfcheck");

  return (
    <>
      <PageHeader eyebrow="VORA · middleware ERP → πωλητής" title="Agent"
        subtitle="Διαβάζει τα τιμολόγια από το ERP, προβλέπει πότε κάθε πελάτης θα ξεμείνει από κάθε είδος, και ετοιμάζει Suggested Orders — μόνος του, κάθε πρωί. Ο πωλητής εγκρίνει.">
        <button type="button" className="btn btn-primary" onClick={start} disabled={running}>
          {running ? <><span className="ai-dots" aria-hidden><i /><i /><i /></span> Τρέχει…</> : "▶ Τρέξε τον agent τώρα"}
        </button>
      </PageHeader>
      <OperationsSummary />

      <div className="reveal grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile label="Τελευταία εκτέλεση" value={run ? when(run.started_at) : "–"}
          note={run ? <>{TRIGGER[run.trigger] ?? run.trigger}{seconds(run) != null && <> · {seconds(run)!.toFixed(1).replace(".", ",")} δευτ.</>} · <RunStatus run={run} /></> : "δεν έχει τρέξει ακόμη"} />
        <StatTile label="Από το ERP" value={n(fetchM.invoices) != null ? <>{fmtNum(n(fetchM.invoices))} <span className="text-base font-normal text-ink-2">τιμολόγια</span></> : run?.source === "csv" ? "CSV" : "–"}
          note={n(fetchM.lines) != null ? `${fmtNum(n(fetchM.lines))} γραμμές · ${n(fetchM.pages)} σελίδες API` : run?.source === "csv" ? "το ERP δεν απάντησε — διάβασε τα CSV" : undefined} />
        <StatTile label="Suggested Orders" value={n(sum.suggestions) != null ? fmtNum(n(sum.suggestions)) : "–"}
          note={n(sum.suggestions) != null ? <><strong className="text-ink">{n(sum.critical)} κρίσιμες</strong> · {fmtEur(n(sum.value_eur))}</> : undefined} />
        <StatTile label="Αυτοέλεγχος (backtest)" value={n(self.mae) != null ? <>{(n(self.mae)!).toFixed(1).replace(".", ",")} <span className="text-base font-normal text-ink-2">μέρες MAE</span></> : "–"}
          note={st.data.schedule ? `όριο ${String(self.limit ?? 4).replace(".", ",")} · προγραμματισμός: κάθε μέρα ${st.data.schedule}` : undefined} />
      </div>

      <div className="reveal mt-6 grid gap-6 lg:grid-cols-5">
        <Card className="lg:col-span-3" title="Βήματα" subtitle={run ? `${run.id ?? "νέα εκτέλεση"}` : undefined}>
          {!run ? <p className="text-sm text-ink-2">Πάτα «Τρέξε τον agent τώρα».</p> : <Timeline run={run} />}
          {run?.warnings?.length ? (
            <ul className="mt-3 space-y-1 text-sm" role="alert">
              {run.warnings.map((w, i) => <li key={i} className="text-ink-2"><span aria-hidden style={{ color: "var(--warning)" }}>!</span> {w}</li>)}
            </ul>
          ) : null}
          {run?.status === "done" && (
            <div className="fade-in mt-4 flex flex-wrap gap-2">
              <Link href="/orders" className="btn btn-primary btn-sm">Δες τις προτάσεις →</Link>
              <Link href="/evaluation" className="btn btn-ghost btn-sm">Αξιολόγηση</Link>
            </div>
          )}
        </Card>

        <div className="space-y-6 lg:col-span-2">
          <Card title="Κανόνες ασφαλείας">
            <ul className="space-y-2.5 text-sm text-ink-2">
              <li><strong className="text-ink">Δεν παραγγέλνει μόνος του.</strong> Ετοιμάζει προτάσεις· draft στο ERP γίνεται μόνο όταν εγκρίνει ο πωλητής (dashboard ή φωνή), μία φορά, με token.</li>
              <li><strong className="text-ink">Ελέγχει πριν δείξει.</strong> Κάθε πρόταση περνά από τους κανόνες του ERP: γνωστός πελάτης & είδη, ποσότητα &gt; 0, παράδοση σε εργάσιμη και πριν την εξάντληση.</li>
              <li><strong className="text-ink">Σταματά αν κάτι χαλάσει.</strong> Αν το backtest ξεπεράσει το όριο λάθους, δεν δημοσιεύει τίποτα και μένουν οι προηγούμενες προτάσεις.</li>
              <li><strong className="text-ink">Κρατά τη δουλειά του πωλητή.</strong> Ιστορικό και drafts διατηρούνται. Αλλαγμένη πρόταση χρειάζεται νέα έγκριση· έγκυρες αλλαγές ποσότητας μένουν.</li>
            </ul>
          </Card>
          <Card title="Ιστορικό">
            {st.data.runs.length === 0 ? <p className="text-sm text-ink-2">Καμία εκτέλεση ακόμη.</p> : (
              <ul className="-my-1 divide-y divide-[var(--grid)]">
                {st.data.runs.slice(0, 6).map((r) => (
                  <li key={r.id ?? r.started_at} className="flex items-center justify-between gap-3 py-2 text-sm">
                    <span className="min-w-0">
                      <span className="block text-ink tnum">{when(r.started_at)}</span>
                      <span className="block truncate text-xs text-ink-muted">{TRIGGER[r.trigger] ?? r.trigger} · {r.source === "erp" ? "από ERP" : "από CSV"}</span>
                    </span>
                    <span className="shrink-0 text-right text-xs text-ink-2">
                      {r.summary?.suggestions != null && <span className="block tnum">{r.summary.suggestions} προτάσεις</span>}
                      <RunStatus run={r as AgentRun} />
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}

function RunStatus({ run }: { run: Pick<AgentRun, "status"> }) {
  const m = { running: ["◌", "τρέχει", "var(--series-1)"], done: ["✓", "ολοκληρώθηκε", "var(--good)"], error: ["!", "σταμάτησε", "var(--critical)"] }[run.status];
  return <span className="whitespace-nowrap"><span aria-hidden style={{ color: m[2] }}>{m[0]}</span> {m[1]}</span>;
}

function Timeline({ run }: { run: AgentRun }) {
  const plan = run.plan.length ? run.plan : [{ key: "fetch", label: "Διάβασμα από το ERP" }];
  const firstPending = plan.findIndex((p) => !run.steps[p.key]);
  return (
    <ol className="relative">
      {plan.map((p, i) => {
        const s: AgentStep | undefined = run.steps[p.key];
        const state: string = s?.status ?? (run.status === "error" ? "skipped" : run.status === "running" && i === firstPending ? "next" : "pending");
        const prog = run.progress?.[p.key];
        return (
          <li key={p.key} className="relative flex gap-3 pb-5 last:pb-0">
            {i < plan.length - 1 && (
              <span aria-hidden className="absolute left-[13px] top-7 h-[calc(100%-1.75rem)] w-px"
                style={{ background: s?.status === "done" ? "var(--good)" : "var(--grid)", transition: "background 300ms" }} />
            )}
            <StepIcon state={state} />
            <div className="min-w-0 flex-1 pt-0.5">
              <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                <span className={`text-sm font-semibold ${state === "pending" || state === "skipped" ? "text-ink-muted" : "text-ink"}`}>{i + 1}. {p.label}</span>
                {s?.ms != null && s.status !== "running" && <span className="text-xs text-ink-muted tnum">{s.ms < 1000 ? `${s.ms} ms` : `${(s.ms / 1000).toFixed(1).replace(".", ",")} δευτ.`}</span>}
              </div>
              {s?.status === "running" && prog?.total ? (
                <div className="mt-1.5">
                  <div className="h-1.5 w-full overflow-hidden rounded-full" style={{ background: "var(--series-1-wash)" }}>
                    <div className="h-full rounded-full" style={{ width: `${Math.round(((prog.done ?? 0) / prog.total) * 100)}%`, background: "var(--series-1)", transition: "width 200ms" }} />
                  </div>
                  <div className="mt-1 text-xs text-ink-muted">{prog.detail}</div>
                </div>
              ) : s?.detail ? (
                <p className={`fade-in mt-0.5 text-sm ${s.status === "error" ? "text-ink" : "text-ink-2"}`}>{s.detail}</p>
              ) : state === "skipped" ? <p className="mt-0.5 text-xs text-ink-muted">δεν έτρεξε</p> : null}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function StepIcon({ state }: { state: string }) {
  const base = "relative z-10 flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold";
  if (state === "done") return <span className={`${base} fade-in text-white`} style={{ background: "var(--good)" }} aria-label="έγινε">✓</span>;
  if (state === "error") return <span className={`${base} text-white`} style={{ background: "var(--critical)" }} aria-label="σφάλμα">!</span>;
  if (state === "running" || state === "next")
    return <span className={`${base} pulse-dot border-2`} style={{ borderColor: "var(--series-1)", background: "var(--series-1-wash)", color: "var(--series-1)" }} aria-label="τρέχει">◌</span>;
  return <span className={`${base} border border-line bg-surface-2 text-ink-muted`} aria-label="σε αναμονή">○</span>;
}
