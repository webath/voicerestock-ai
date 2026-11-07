"use client";
import { useState } from "react";
import { Card, EmptyState, ErrorBox, Loading, PageHeader, Select, StatTile } from "@/components/ui";
import { useToast } from "@/components/Toast";
import { ApiError, apiPost, useApi, usePolling } from "@/lib/api";
import { fmtNum } from "@/lib/format";

// Owner: Νίκος. Δεδομένα: GET /api/market (poll όσο τρέχει), POST /api/market/scan. Ο agent: apps/api/app/market.py.

interface Source { i: number; url: string; title: string; page_age: string | null }
interface PriceOutlook { category: string; direction: "up" | "down" | "stable" | "mixed"; horizon: string; signal: string; action: string; sources: number[] }
interface Competitor { name: string; move: string; impact: string; action: string; sources: number[] }
interface NewProduct { product: string; trend: string; fit: string; action: string; sources: number[] }
interface Weakness { title: string; our_data: string; market: string; action: string; sources: number[] }
interface Scan {
  id: string; trigger: string; started_at: string; finished_at?: string; status: "running" | "done" | "error"; error?: string;
  report?: { summary: string; price_outlook: PriceOutlook[]; competitors: Competitor[]; new_products: NewProduct[]; weaknesses: Weakness[] };
  sources?: Source[]; searches?: number; usage?: { input_tokens: number; output_tokens: number };
}
interface MarketState {
  running: boolean; current: (Scan & { step?: string }) | null; has_credentials: boolean; model: string;
  every_days: number; next_run_at: string | null; scan: Scan | null; history: Scan[];
}

const DIR: Record<PriceOutlook["direction"], { icon: string; label: string; color: string }> = {
  up: { icon: "↑", label: "Ανεβαίνουν", color: "var(--critical)" },
  down: { icon: "↓", label: "Πέφτουν", color: "var(--good)" },
  stable: { icon: "→", label: "Σταθερές", color: "var(--ink-muted)" },
  mixed: { icon: "⇅", label: "Ανάμεικτα σήματα", color: "var(--serious)" },
};
const TRIGGER: Record<string, string> = { manual: "χειροκίνητα", schedule: "εβδομαδιαία" };

function when(iso?: string | null) {
  if (!iso) return "–";
  const d = new Date(iso);
  return `${d.getDate()}/${d.getMonth() + 1} · ${d.toLocaleTimeString("el-GR", { hour: "2-digit", minute: "2-digit" })}`;
}

export default function MarketPage() {
  const [scanId, setScanId] = useState<string>("");
  const st = useApi<MarketState>(`/api/market${scanId ? `?scan=${scanId}` : ""}`);
  const toast = useToast();
  const [starting, setStarting] = useState(false);
  const running = !!st.data?.running || starting;
  usePolling(st.reload, running ? 1500 : 30000);

  async function start() {
    setStarting(true);
    try {
      await apiPost("/api/market/scan");
      setScanId("");
      st.reload();
    } catch (e) {
      toast({ kind: "error", title: e instanceof ApiError && e.status === 409 ? "Η έρευνα τρέχει ήδη" : "Δεν ξεκίνησε", text: (e as Error).message });
    } finally {
      setTimeout(() => setStarting(false), 800);
    }
  }

  if (st.error) return <ErrorBox message={st.error} />;
  if (!st.data) return <Loading />;
  const d = st.data;
  const scan = d.scan;
  const rep = scan?.status === "done" ? scan.report : undefined;
  const src = new Map((scan?.sources ?? []).map((s) => [s.i, s]));
  const Refs = ({ ids }: { ids: number[] }) => (
    <span className="ml-1 inline-flex flex-wrap gap-1 align-baseline">
      {ids.map((i) => src.get(i) && (
        <a key={i} href={src.get(i)!.url} target="_blank" rel="noreferrer" title={src.get(i)!.title}
          className="rounded-md border border-line bg-surface-2 px-1.5 text-[11px] text-ink-2 tnum hover:text-ink">{i}</a>
      ))}
    </span>
  );

  return (
    <>
      <PageHeader eyebrow="VORA · έρευνα αγοράς" title="Market Scan"
        subtitle={<>Κάθε {d.every_days > 0 ? (d.every_days === 7 ? "εβδομάδα" : `${d.every_days} μέρες`) : "φορά που το ζητάς"} ο agent ψάχνει στο internet τάσεις τιμών, ανταγωνιστές και νέα προϊόντα, και τα διασταυρώνει με τα δικά μας δεδομένα πωλήσεων. Κάθε εύρημα έχει πηγή.</>}>
        <button type="button" className="btn btn-primary" onClick={start} disabled={running || !d.has_credentials}>
          {running ? <><span className="ai-dots" aria-hidden><i /><i /><i /></span> Ψάχνει…</> : "🔎 Σκάναρε τώρα"}
        </button>
      </PageHeader>

      {!d.has_credentials && (
        <Card className="mb-5" title="Λείπει το κλειδί Anthropic" subtitle="Η έρευνα χρειάζεται Claude με web search.">
          <ol className="list-decimal space-y-1 pl-5 text-sm text-ink-2">
            <li>Στο αρχείο <code>.env</code> στη ρίζα του repo: <code>ANTHROPIC_API_KEY=sk-ant-…</code></li>
            <li>Ξεκίνα ξανά το backend: <code>./scripts/dev_backend.sh</code></li>
          </ol>
        </Card>
      )}

      <div className="reveal grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile label="Τελευταία έρευνα" value={scan ? when(scan.started_at) : "–"} note={scan ? TRIGGER[scan.trigger] ?? scan.trigger : "δεν έχει γίνει ακόμα"} />
        <StatTile label="Επόμενη" value={d.every_days > 0 ? when(d.next_run_at) : "κλειστό"} note={d.every_days > 0 ? `κάθε ${d.every_days} μέρες` : "MARKET_SCAN_EVERY_DAYS=0"} />
        <StatTile label="Πηγές" value={fmtNum(scan?.sources?.length ?? 0)} note={scan?.searches != null ? `${scan.searches} αναζητήσεις στο web` : undefined} />
        <StatTile label="Ευρήματα" value={rep ? fmtNum(rep.price_outlook.length + rep.competitors.length + rep.new_products.length + rep.weaknesses.length) : "–"}
          note={rep ? `${rep.weaknesses.length} αδυναμίες μας` : undefined} />
      </div>

      {d.history.length > 1 && (
        <div className="fade-in mt-5 flex items-center gap-2 text-sm text-ink-2">
          Έρευνα:
          <Select label="Παλιότερη έρευνα" value={scanId} onChange={setScanId} options={[
            { value: "", label: "Η πιο πρόσφατη" },
            ...d.history.map((h) => ({ value: h.id, label: `${when(h.started_at)}${h.status === "error" ? " · απέτυχε" : ""}` })),
          ]} />
        </div>
      )}

      {d.current && (
        <div className="card fade-in mt-5 flex items-center gap-3 p-4 text-sm text-ink-2" role="status">
          <span className="ai-dots" aria-hidden><i /><i /><i /></span>
          {d.current.step ?? "Τρέχει…"} <span className="text-ink-muted">(1–3 λεπτά)</span>
        </div>
      )}

      {scan?.status === "error" && (
        <div className="card mt-5 p-4 text-sm text-ink-2" role="alert"><strong className="text-ink">Η έρευνα απέτυχε.</strong> {scan.error}</div>
      )}

      {!scan && !d.current && (
        <div className="mt-6"><EmptyState title="Δεν έχει γίνει ακόμα έρευνα αγοράς">Πάτα «Σκάναρε τώρα» — ή περίμενε την εβδομαδιαία εκτέλεση.</EmptyState></div>
      )}

      {rep && (
        <div className="mt-6 space-y-6">
          <section className="card ai-gradient fade-in p-5">
            <div className="text-xs font-medium uppercase tracking-[0.14em] text-ink-muted">Σύνοψη εβδομάδας</div>
            <p className="mt-2 text-[15px] leading-relaxed text-ink">{rep.summary}</p>
          </section>

          <Card title="Τάσεις τιμών στην αγορά" subtitle="Τι έρχεται ανά κατηγορία και τι να κάνουμε πριν φτάσει στους πελάτες μας.">
            <div className="grid gap-3 md:grid-cols-2">
              {rep.price_outlook.map((p, k) => (
                <div key={k} className="rounded-xl border border-line bg-surface-2 p-4">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold text-ink">{p.category}</span>
                    <span className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border border-line bg-surface px-2 py-0.5 text-xs text-ink-2">
                      <span aria-hidden className="font-semibold" style={{ color: DIR[p.direction].color }}>{DIR[p.direction].icon}</span>{DIR[p.direction].label} · {p.horizon}
                    </span>
                  </div>
                  <p className="mt-2 text-sm text-ink-2">{p.signal}<Refs ids={p.sources} /></p>
                  <p className="mt-2 text-sm text-ink">→ {p.action}</p>
                </div>
              ))}
            </div>
          </Card>

          <Card title="Αδυναμίες μας" subtitle="Η αγορά διασταυρωμένη με τα δικά μας δεδομένα πωλήσεων.">
            <div className="space-y-3">
              {rep.weaknesses.map((w, k) => (
                <div key={k} className="rounded-xl border border-line bg-surface-2 p-4">
                  <div className="font-semibold text-ink">{w.title}</div>
                  <div className="mt-2 grid gap-3 text-sm sm:grid-cols-2">
                    <div><div className="text-xs text-ink-muted">Τα δεδομένα μας</div><div className="text-ink-2">{w.our_data}</div></div>
                    <div><div className="text-xs text-ink-muted">Η αγορά</div><div className="text-ink-2">{w.market}<Refs ids={w.sources} /></div></div>
                  </div>
                  <p className="mt-2 text-sm text-ink">→ {w.action}</p>
                </div>
              ))}
              {!rep.weaknesses.length && <p className="text-sm text-ink-muted">Καμία αδυναμία αυτή την εβδομάδα.</p>}
            </div>
          </Card>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card title="Ανταγωνιστές">
              <ul className="space-y-3 text-sm">
                {rep.competitors.map((c, k) => (
                  <li key={k} className="border-b border-line pb-3 last:border-0 last:pb-0">
                    <div className="font-semibold text-ink">{c.name}</div>
                    <div className="text-ink-2">{c.move}<Refs ids={c.sources} /></div>
                    <div className="mt-1 text-ink-muted">Επίπτωση: {c.impact}</div>
                    <div className="mt-1 text-ink">→ {c.action}</div>
                  </li>
                ))}
                {!rep.competitors.length && <li className="text-ink-muted">Δεν βρέθηκαν κινήσεις με πηγή.</li>}
              </ul>
            </Card>
            <Card title="Νέα προϊόντα & τάσεις">
              <ul className="space-y-3 text-sm">
                {rep.new_products.map((n, k) => (
                  <li key={k} className="border-b border-line pb-3 last:border-0 last:pb-0">
                    <div className="font-semibold text-ink">{n.product}</div>
                    <div className="text-ink-2">{n.trend}<Refs ids={n.sources} /></div>
                    <div className="mt-1 text-ink-muted">Για εμάς: {n.fit}</div>
                    <div className="mt-1 text-ink">→ {n.action}</div>
                  </li>
                ))}
                {!rep.new_products.length && <li className="text-ink-muted">Δεν βρέθηκαν νέα προϊόντα με πηγή.</li>}
              </ul>
            </Card>
          </div>

          <Card title="Πηγές" subtitle={`${scan?.sources?.length ?? 0} σελίδες από την αναζήτηση · ${scan?.usage ? `${fmtNum(scan.usage.input_tokens + scan.usage.output_tokens)} tokens · ` : ""}${d.model}`}>
            <ol className="space-y-1 text-sm">
              {(scan?.sources ?? []).map((s) => (
                <li key={s.i} className="flex gap-2">
                  <span className="w-6 shrink-0 text-right text-ink-muted tnum">{s.i}.</span>
                  <a href={s.url} target="_blank" rel="noreferrer" className="min-w-0 truncate text-ink-2 hover:text-ink hover:underline">{s.title}</a>
                  {s.page_age && <span className="shrink-0 text-ink-muted">· {s.page_age}</span>}
                </li>
              ))}
            </ol>
          </Card>
        </div>
      )}
    </>
  );
}
