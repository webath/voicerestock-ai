"use client";
import Link from "next/link";
import { Fragment, useEffect, useState } from "react";
import { Card, Chip, EmptyState, ErrorBox, Loading, PageHeader, Segmented, StatTile } from "@/components/ui";
import { useToast } from "@/components/Toast";
import { useApi } from "@/lib/api";
import { fmt1, fmtDay, fmtDayLong, fmtEur, fmtEur2, fmtNum } from "@/lib/format";

// Owner: Νίκος. Δεδομένα: GET /api/campaigns (apps/api/app/campaigns.py) — όλα από το ιστορικό τιμολογίων, χωρίς LLM.

interface Customer { TRDR: number; CUSTOMER_NAME: string; CUSTOMER_CATEGORY: string; AREA: string; CITY: string; SALESMAN: number; SALESMAN_NAME: string | null }
interface Item { MTRL: number; ITEM_NAME: string; CATEGORY: string; UNIT: string; PRICE: number }
interface SeasonalItem extends Item {
  uplift: number; past_window_qty: number; past_years: number[]; suggested_disc: number; disc_basis: string;
  promo_from: string; promo_to: string; already_scheduled: string | null; targets: (Customer & { past_qty: number })[];
}
interface SeasonalEvent { event: string; date: string; days_until: number; holidays: string[]; past_years: number[]; total_uplift: number | null; items: SeasonalItem[] }
interface Pricing extends Item {
  action: "increase" | "promo" | "review"; change_pct: number | null; why: string; yoy: number; yoy_typical: number;
  qty_12w: number; qty_12w_last_year: number; last_price_change_pct: number | null; months_since_price_change: number | null; promo_uplift: number | null;
}
interface AlertItem extends Item { cycle_days: number; days_since: number; ratio: number; last_purchase: string }
interface Alert extends Customer {
  items: AlertItem[]; monthly_value: number; items_broken: number; max_ratio: number; days_since_any_purchase: number;
  severity: "high" | "medium"; kind: "lost" | "partial"; action: string;
}
interface Promo { PROMO: number; NAME: string; CATEGORY: string; FROM: string; TO: string; DISC_PRC: number; per_day_before: number; per_day_during: number; uplift: number }
interface Report { today: string; data_until: string; seasonal: SeasonalEvent[]; pricing: Pricing[]; alerts: Alert[]; promos: Promo[] }

type Tab = "seasonal" | "pricing" | "alerts" | "promos";
const signed = (v: number) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(Math.round(v * 100))}%`;
const ICON: Record<string, string> = { Χριστούγεννα: "🎄", Πρωτοχρονιά: "🥂", Θεοφάνεια: "✝", "Καθαρά Δευτέρα": "🪁", Πάσχα: "🐣" };
const UNIT: Record<string, string> = { ΚΙΒ: "κιβ.", ΤΕΜ: "τεμ." };
const unit = (u: string) => UNIT[u] ?? u.toLowerCase();
const icon = (name: string) => Object.entries(ICON).find(([k]) => name.startsWith(k))?.[1] ?? "📅";

export default function CampaignsPage() {
  const r = useApi<Report>("/api/campaigns");
  const [tab, setTab] = useState<Tab>("seasonal");
  const [email, setEmail] = useState<{ subject: string; body: string; to: string } | null>(null);

  if (r.error) return <ErrorBox message={r.error} />;
  if (!r.data) return <Loading />;
  const d = r.data;
  const next = d.seasonal[0];
  const inc = d.pricing.filter((p) => p.action === "increase").length;
  const lost = d.alerts.filter((a) => a.kind === "lost").length;

  return (
    <>
      <PageHeader eyebrow="VORA · προσφορές & τιμές" title="Campaigns"
        subtitle={<>Προτάσεις για προσφορές, τιμές και πελάτες που χάνουμε — μόνο από το ιστορικό τιμολογίων (δεδομένα ως {fmtDay(d.data_until)}). Το κείμενο του email το στέλνει ο πωλητής· τίποτα δεν φεύγει αυτόματα.</>} />

      <div className="reveal grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile label="Επόμενη γιορτή" value={next ? `${icon(next.event)} ${next.event.split(" & ")[0]}` : "–"}
          note={next ? `σε ${next.days_until} μέρες · ${next.items.length} είδη για προσφορά` : undefined} />
        <StatTile label="Προτάσεις τιμών" value={fmtNum(d.pricing.length)} note={`${inc} αυξήσεις · ${d.pricing.length - inc} προσφορές/έλεγχοι`} />
        <StatTile label="Κύκλος που έσπασε" value={fmtNum(d.alerts.length)} note={`πελάτες · ${lost} πιθανή απώλεια`} />
        <StatTile label="Αξία σε κίνδυνο / μήνα" value={fmtEur(d.alerts.reduce((s, a) => s + a.monthly_value, 0))}
          note="όσα αγόραζαν τακτικά και σταμάτησαν" />
      </div>

      <div className="fade-in my-6 max-w-full overflow-x-auto">
        <Segmented label="Ενότητα" value={tab} onChange={setTab} options={[
          { value: "seasonal", label: "Εποχικές προσφορές" },
          { value: "pricing", label: "Τιμές" },
          { value: "alerts", label: `Ειδοποιήσεις κύκλου (${d.alerts.length})` },
          { value: "promos", label: "Τι απέδωσε" },
        ]} />
      </div>

      {tab === "seasonal" && <Seasonal events={d.seasonal} onEmail={setEmail} />}
      {tab === "pricing" && <PricingTable rows={d.pricing} />}
      {tab === "alerts" && <Alerts rows={d.alerts} onEmail={setEmail} />}
      {tab === "promos" && <Promos rows={d.promos} />}
      {email && <EmailDraft {...email} onClose={() => setEmail(null)} />}
    </>
  );
}

// ---------------- εποχικές ----------------
function Seasonal({ events, onEmail }: { events: SeasonalEvent[]; onEmail: (e: { subject: string; body: string; to: string }) => void }) {
  const [open, setOpen] = useState<string | null>(null);
  if (!events.length) return <EmptyState title="Καμία γιορτή με ιστορική άνοδο στους επόμενους μήνες" />;
  return (
    <div className="space-y-5">
      {events.map((e) => (
        <Card key={e.event + e.date} lift
          title={<>{icon(e.event)} {e.event} · {fmtDayLong(e.date)}</>}
          subtitle={`σε ${e.days_until} μέρες · τι πουλήθηκε τις 2 εβδομάδες πριν, τα ${e.past_years.join(", ")}, σε σύγκριση με τις 8 εβδομάδες πριν από αυτές`}>
          <div className="overflow-x-auto">
            <table className="data">
              <thead><tr>
                <th>Είδος</th><th className="num">Άνοδος πριν τη γιορτή</th><th className="num">Πωλήσεις τότε (μ.ό./χρόνο)</th>
                <th>Προτεινόμενη προσφορά</th><th className="num">Πελάτες-στόχος</th>
              </tr></thead>
              <tbody>
                {e.items.map((it) => {
                  const key = `${e.event}-${it.MTRL}`;
                  return (
                    <Fragment key={key}>
                      <tr>
                        <td><div className="font-medium text-ink">{it.ITEM_NAME}</div><div className="text-xs text-ink-muted">{it.CATEGORY}</div></td>
                        <td className="num tnum font-semibold text-ink">×{fmt1(it.uplift)}</td>
                        <td className="num tnum">{fmtNum(it.past_window_qty)} {unit(it.UNIT)}</td>
                        <td>
                          <div className="text-ink">−{fmtNum(it.suggested_disc)}% · {fmtDay(it.promo_from)}–{fmtDay(it.promo_to)}</div>
                          <div className="text-xs text-ink-muted">{it.disc_basis}</div>
                          {it.already_scheduled && <div className="mt-1"><Chip title="Υπάρχει ήδη στο PROMO.csv">✓ ήδη: {it.already_scheduled}</Chip></div>}
                        </td>
                        <td className="num">
                          <button type="button" className="btn btn-ghost btn-sm" aria-expanded={open === key} onClick={() => setOpen(open === key ? null : key)}>
                            {it.targets.length} {open === key ? "▴" : "▾"}
                          </button>
                        </td>
                      </tr>
                      {open === key && (
                        <tr><td colSpan={5} className="!bg-surface-2">
                          <div className="grid gap-2 py-1 sm:grid-cols-2">
                            {it.targets.map((t) => (
                              <div key={t.TRDR} className="flex items-center justify-between gap-3 rounded-xl border border-line bg-surface px-3 py-2">
                                <div className="min-w-0">
                                  <Link href={`/customers/${t.TRDR}`} className="font-medium text-ink hover:underline">{t.CUSTOMER_NAME}</Link>
                                  <div className="text-xs text-ink-muted">{t.CUSTOMER_CATEGORY} · {t.CITY} · τότε ~{fmtNum(t.past_qty)} {unit(it.UNIT)}</div>
                                </div>
                                <button type="button" className="btn btn-sm" onClick={() => onEmail(seasonalEmail(e, it, t))}>✉ Email</button>
                              </div>
                            ))}
                          </div>
                        </td></tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
      ))}
    </div>
  );
}

// ---------------- τιμές ----------------
const ACTION: Record<Pricing["action"], { label: string; icon: string; color: string }> = {
  increase: { label: "Αύξηση τιμής", icon: "↑", color: "var(--good)" },
  promo: { label: "Προσφορά", icon: "%", color: "var(--serious)" },
  review: { label: "Έλεγχος αγοράς", icon: "?", color: "var(--ink-muted)" },
};

function PricingTable({ rows }: { rows: Pricing[] }) {
  if (!rows.length) return <EmptyState title="Καμία πρόταση τιμής" />;
  return (
    <div className="card fade-in overflow-x-auto">
      <table className="data">
        <thead><tr>
          <th>Είδος</th><th className="num">Ζήτηση 12 εβδ. vs πέρυσι</th><th className="num">Τελευταία αλλαγή τιμής</th>
          <th>Πρόταση</th><th>Γιατί</th>
        </tr></thead>
        <tbody>
          {rows.map((p) => {
            const a = ACTION[p.action];
            return (
              <tr key={p.MTRL}>
                <td><div className="font-medium text-ink">{p.ITEM_NAME}</div><div className="text-xs text-ink-muted">{p.CATEGORY} · {fmtEur2(p.PRICE)}/{unit(p.UNIT)}</div></td>
                <td className="num tnum"><span className="font-semibold text-ink">{signed(p.yoy)}</span><div className="text-xs text-ink-muted">κατάλογος {signed(p.yoy_typical)}</div></td>
                <td className="num tnum">{p.last_price_change_pct != null ? signed(p.last_price_change_pct) : "–"}<div className="text-xs text-ink-muted">πριν {p.months_since_price_change ?? "–"} μήνες</div></td>
                <td>
                  <span className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border border-line bg-surface-2 px-2 py-0.5 text-xs text-ink-2">
                    <span aria-hidden style={{ color: a.color }} className="font-semibold">{a.icon}</span>{a.label}{p.change_pct != null ? ` ${signed(p.change_pct)}` : ""}
                  </span>
                  {p.change_pct != null && <div className="mt-1 text-xs text-ink-muted tnum">{fmtEur2(p.PRICE)} → {fmtEur2(p.PRICE * (1 + p.change_pct))}</div>}
                </td>
                <td className="max-w-sm text-sm text-ink-2">{p.why}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ---------------- ειδοποιήσεις κύκλου ----------------
function Alerts({ rows, onEmail }: { rows: Alert[]; onEmail: (e: { subject: string; body: string; to: string }) => void }) {
  const [sev, setSev] = useState<"high" | "all">("high");
  const shown = rows.filter((a) => sev === "all" || a.severity === "high");
  if (!rows.length) return <EmptyState title="Κανένας κύκλος δεν έσπασε" />;
  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Segmented label="Σοβαρότητα" value={sev} onChange={setSev} options={[
          { value: "high", label: `Σοβαρά (${rows.filter((a) => a.severity === "high").length})` },
          { value: "all", label: `Όλα (${rows.length})` },
        ]} />
        <span className="text-sm text-ink-muted">Είδη που ο πελάτης αγόραζε τακτικά τον τελευταίο χρόνο και τώρα έχει περάσει πάνω από το διπλάσιο του κύκλου του — αγόραζε τα ίδια και πέρυσι τέτοια εποχή, άρα δεν είναι εποχικό.</span>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        {shown.map((a) => (
          <Card key={a.TRDR} lift
            title={<Link href={`/customers/${a.TRDR}`} className="hover:underline">{a.CUSTOMER_NAME}</Link>}
            subtitle={`${a.CUSTOMER_CATEGORY} · ${a.CITY} · πωλητής ${a.SALESMAN_NAME ?? a.SALESMAN}`}
            action={<span className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border border-line bg-surface-2 px-2 py-0.5 text-xs text-ink-2">
              <span aria-hidden className="font-semibold" style={{ color: a.kind === "lost" ? "var(--critical)" : "var(--serious)" }}>{a.kind === "lost" ? "●" : "◐"}</span>
              {a.kind === "lost" ? "Πιθανή απώλεια" : `${a.items_broken} ${a.items_broken === 1 ? "είδος" : "είδη"}`}
            </span>}>
            <div className="text-sm text-ink-2">
              <span className="font-semibold text-ink tnum">{fmtEur(a.monthly_value)}</span> / μήνα σε κίνδυνο ·
              τελευταία αγορά οτιδήποτε πριν {a.days_since_any_purchase} μέρες
            </div>
            <ul className="mt-3 space-y-1.5 text-sm">
              {a.items.slice(0, 4).map((i) => (
                <li key={i.MTRL} className="flex justify-between gap-3">
                  <span className="min-w-0 truncate text-ink">{i.ITEM_NAME}</span>
                  <span className="whitespace-nowrap text-ink-muted tnum">κάθε {i.cycle_days} μ. · τώρα {i.days_since} μ. (×{fmt1(i.ratio)})</span>
                </li>
              ))}
              {a.items.length > 4 && <li className="text-ink-muted">και άλλα {a.items.length - 4} είδη</li>}
            </ul>
            <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-line pt-3">
              <span className="text-sm text-ink-2">→ {a.action}</span>
              <button type="button" className="btn btn-sm" onClick={() => onEmail(winbackEmail(a))}>✉ Email επαναφοράς</button>
            </div>
          </Card>
        ))}
      </div>
    </>
  );
}

// ---------------- τι απέδωσε ----------------
function Promos({ rows }: { rows: Promo[] }) {
  return (
    <Card title="Οι προσφορές του PROMO.csv" subtitle="Πωλήσεις ανά μέρα των ειδών της προσφοράς, κατά τη διάρκειά της σε σύγκριση με τις 6 εβδομάδες πριν. Από εδώ βγαίνει η προτεινόμενη έκπτωση ανά κατηγορία.">
      <div className="overflow-x-auto">
        <table className="data">
          <thead><tr><th>Προσφορά</th><th>Διάρκεια</th><th className="num">Έκπτωση</th><th className="num">Πριν / μέρα</th><th className="num">Στην προσφορά / μέρα</th><th className="num">Άνοδος</th></tr></thead>
          <tbody>
            {rows.map((p) => (
              <tr key={p.PROMO}>
                <td><div className="text-ink">{p.NAME}</div><div className="text-xs text-ink-muted">{p.CATEGORY}</div></td>
                <td className="tnum whitespace-nowrap">{fmtDay(p.FROM)} – {fmtDay(p.TO)} {p.FROM.slice(0, 4)}</td>
                <td className="num tnum">−{fmtNum(p.DISC_PRC)}%</td>
                <td className="num tnum">{fmt1(p.per_day_before)}</td>
                <td className="num tnum">{fmt1(p.per_day_during)}</td>
                <td className="num tnum font-semibold text-ink">×{fmt1(p.uplift)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

// ---------------- email (κείμενο για τον πωλητή — δεν στέλνεται αυτόματα) ----------------
function seasonalEmail(e: SeasonalEvent, it: SeasonalItem, t: Customer & { past_qty: number }) {
  const event = e.event.split(" & ")[0];
  return {
    to: t.CUSTOMER_NAME,
    subject: `Προσφορά −${fmtNum(it.suggested_disc)}% για ${event}: ${it.ITEM_NAME}`,
    body: `Καλησπέρα σας,

Ενόψει ${event.startsWith("Πάσχα") ? "του Πάσχα" : event === "Χριστούγεννα" ? "των Χριστουγέννων" : `της γιορτής (${event})`}, ετοιμάσαμε για το ${t.CUSTOMER_NAME} προσφορά −${fmtNum(it.suggested_disc)}% στο «${it.ITEM_NAME}» για παραγγελίες από ${fmtDay(it.promo_from)} έως ${fmtDay(it.promo_to)}.

Τις προηγούμενες χρονιές, την ίδια περίοδο, παραγγείλατε περίπου ${fmtNum(t.past_qty)} ${unit(it.UNIT) === "κιβ." ? "κιβώτια" : unit(it.UNIT)}. Αν θέλετε, κλείνουμε από τώρα την ποσότητα και την ημέρα παράδοσης ώστε να είστε έτοιμοι για τις γιορτές.

Είμαι στη διάθεσή σας για οτιδήποτε χρειαστείτε.

${t.SALESMAN_NAME ?? ""}
DEMO ΔΙΑΝΟΜΕΣ Α.Ε.`,
  };
}

function winbackEmail(a: Alert) {
  const names = a.items.slice(0, 3).map((i) => `«${i.ITEM_NAME}»`).join(", ");
  return {
    to: a.CUSTOMER_NAME,
    subject: a.kind === "lost" ? `${a.CUSTOMER_NAME}: μας λείψατε` : `${a.CUSTOMER_NAME}: ειδική τιμή για ${a.items_broken === 1 ? "ένα είδος" : "είδη"} που παίρνατε`,
    body: `Καλησπέρα σας,

${a.kind === "lost"
      ? "Παρατηρήσαμε ότι έχει περάσει αρκετός καιρός από την τελευταία σας παραγγελία και θέλαμε να δούμε αν όλα πάνε καλά και αν μπορούμε να βοηθήσουμε σε κάτι."
      : `Παρατηρήσαμε ότι τον τελευταίο καιρό δεν παραγγέλνετε από εμάς ${names}${a.items.length > 3 ? " και κάποια ακόμα είδη" : ""}.`}

Θα θέλαμε να σας κάνουμε μια ειδική πρόταση τιμής${a.kind === "lost" ? " για την επόμενη παραγγελία σας" : " για αυτά τα είδη"}. Μπορούμε να μιλήσουμε τηλεφωνικά αυτή την εβδομάδα;

${a.SALESMAN_NAME ?? ""}
DEMO ΔΙΑΝΟΜΕΣ Α.Ε.`,
  };
}

function EmailDraft({ to, subject, body, onClose }: { to: string; subject: string; body: string; onClose: () => void }) {
  const toast = useToast();
  const [text, setText] = useState(body);
  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [onClose]);
  async function copy() {
    try {
      await navigator.clipboard.writeText(`${subject}\n\n${text}`);
      toast({ kind: "success", title: "Αντιγράφηκε", text: "Επικόλλησέ το στο email σου." });
    } catch {
      toast({ kind: "error", title: "Δεν αντιγράφηκε", text: "Επίλεξε το κείμενο και αντέγραψέ το με το χέρι." });
    }
  }
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 p-4 backdrop-blur-[3px]" onClick={onClose} role="presentation">
      <div className="card w-full max-w-xl p-5" role="dialog" aria-modal aria-label="Email προς πελάτη" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="text-xs text-ink-muted">Προς: {to} · το στέλνει ο πωλητής</div>
            <h2 className="mt-0.5 text-base font-semibold text-ink">{subject}</h2>
          </div>
          <button type="button" className="btn btn-ghost btn-sm" onClick={onClose} aria-label="Κλείσιμο">✕</button>
        </div>
        <textarea className="field mt-3 !h-72 w-full resize-y py-2 leading-relaxed" value={text} onChange={(e) => setText(e.target.value)} aria-label="Κείμενο email" />
        <div className="mt-3 flex flex-wrap justify-end gap-2">
          <a className="btn" href={`mailto:?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(text)}`}>Άνοιγμα στο email</a>
          <button type="button" className="btn btn-primary" onClick={copy}>Αντιγραφή</button>
        </div>
      </div>
    </div>
  );
}
