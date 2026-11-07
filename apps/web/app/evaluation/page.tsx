"use client";
import { MaeBarChart } from "@/components/charts/MaeBarChart";
import { Card, ErrorBox, Loading, PageHeader, StatTile } from "@/components/ui";
import { useApi, type Evaluation } from "@/lib/api";
import { fmt1, fmtDay, fmtNum, fmtPct, MODEL_LABELS } from "@/lib/format";

// Owner: Δημήτρης. Δεδομένα: GET /api/evaluation (τοπικό backtest, docs/RESULTS.md).
export default function EvaluationPage() {
  const { data, error } = useApi<Evaluation>("/api/evaluation");
  if (error) return <ErrorBox message={error} />;
  if (!data) return <Loading />;

  const cur = data.rows.find((r) => r.model === data.default_model)!;
  const base = data.rows.find((r) => r.model === "baseline_180");
  const gain = base ? 1 - cur.mae / base.mae : null;
  const perCut = data.per_cutoff.filter((r) => r.model === data.default_model || r.model === "baseline_180");
  const cutoffs = [...new Set(perCut.map((r) => r.cutoff))];

  return (
    <>
      <PageHeader
        title="Αξιολόγηση μοντέλου"
        subtitle={<>Τοπικό backtest σε {data.cutoffs.length} ψεύτικα cutoffs της ίδιας εποχής ({data.cutoffs.map(fmtDay).join(", ")}). Το επίσημο σκορ το υπολογίζει η Revival.</>}
      />

      <div className="reveal grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile hero label="Μέσο λάθος (MAE)" value={<>{fmt1(cur.mae)} <span className="text-lg font-normal text-ink-2">μέρες</span></>}
          note={`${MODEL_LABELS[cur.model] ?? cur.model}`} />
        <StatTile label="Baseline 180 ημερών" value={<>{fmt1(base?.mae)} <span className="text-base font-normal text-ink-2">μέρες</span></>}
          note={gain != null ? <span style={{ color: "var(--good-text)" }}>▼ {fmtPct(gain)} μικρότερο λάθος</span> : undefined} />
        <StatTile label="Προβλέψεις εντός ±7 ημερών" value={fmtPct(cur.within_7)} note={`εντός ±3: ${fmtPct(cur.within_3)}`} />
        <StatTile label="Κάλυψη ζευγών" value={`${fmtNum(data.coverage.pairs)} / ${fmtNum(data.coverage.targets)}`}
          note={`${fmtNum(data.coverage.with_date)} με ημερομηνία · ${fmtNum(data.coverage.blank)} χωρίς εξάντληση σε 90 μέρες`} />
      </div>

      <div className="reveal mt-6 grid gap-6 lg:grid-cols-5">
        <Card className="lg:col-span-3" title="Μέσο λάθος ανά μοντέλο" subtitle="Μέρες, μικρότερο = καλύτερο. Μέσος όρος των cutoffs.">
          <MaeBarChart rows={data.rows} current={data.default_model} />
        </Card>
        <Card className="lg:col-span-2" title="Πώς διαβάζεται">
          <ul className="space-y-3 text-sm text-ink-2">
            <li><strong className="text-ink">Τι μετράμε.</strong> Για κάθε ζεύγος πελάτη × είδους, πόσες μέρες απέχει η πρόβλεψη από την πραγματική εξάντληση — όπως στη βαθμολόγηση του διαγωνισμού.</li>
            <li><strong className="text-ink">«Αληθινή» εξάντληση στο backtest.</strong> Δεν βλέπουμε το απόθεμα του πελάτη. Ο πελάτης ξαναπαραγγέλνει λίγο πριν μηδενίσει, οπότε
              «εξάντληση» = επόμενη αγορά + 2 μέρες + 10% του κύκλου του. Το βαθμονομήσαμε ώστε τα δύο σημεία αναφοράς της Revival (cutoff+30 ≈ {fmt1(data.readme_reference["cutoff+30"])},
              baseline ≈ {fmt1(data.readme_reference.baseline_180)}) να βγαίνουν κοντά (στα cutoffs Οκτ–Νοε 2025).{data.mae_proxy?.[data.default_model] != null && <> Με σκέτη την επόμενη αγορά το μοντέλο βγάζει {fmt1(data.mae_proxy[data.default_model])}.</>}</li>
            <li><strong className="text-ink">Τι κάνει τη διαφορά.</strong> Ο κύκλος αγορών κάθε πελάτη (στο v5 από ιστορικό 365 ημερών), ο ρυθμός κατανάλωσης από την ίδια περίοδο πέρσι (πιάνει όσους κλείνουν τον χειμώνα),
              οι νέοι πελάτες από παρόμοιους, και η επίδραση των προσφορών: ο μεγαλύτερος κύκλος εκτιμάται από το ιστορικό κατηγορίας και πελάτη–είδους,
              με συντηρητική προσαρμογή και αρχική εκτίμηση ×1,8 όταν λείπουν στοιχεία.</li>
          </ul>
        </Card>
      </div>

      <Card className="mt-6" title="Ανά cutoff" subtitle="Τρέχον μοντέλο έναντι baseline">
        <div className="overflow-x-auto">
          <table className="data">
            <thead>
              <tr>
                <th>Cutoff</th>
                <th className="num">Ζεύγη</th>
                <th className="num">MAE baseline</th>
                <th className="num">MAE μοντέλου</th>
                <th className="num">Εντός ±3</th>
                <th className="num">Εντός ±7</th>
                <th className="num">At Risk precision</th>
                <th className="num">At Risk recall</th>
              </tr>
            </thead>
            <tbody>
              {cutoffs.map((c) => {
                const m = perCut.find((r) => r.cutoff === c && r.model === data.default_model)!;
                const b = perCut.find((r) => r.cutoff === c && r.model === "baseline_180");
                return (
                  <tr key={c}>
                    <td>{fmtDay(c)} {c.slice(0, 4)}</td>
                    <td className="num">{fmtNum(m.n)}</td>
                    <td className="num text-ink-2">{fmt1(b?.mae)}</td>
                    <td className="num font-semibold">{fmt1(m.mae)}</td>
                    <td className="num">{fmtPct(m.within_3)}</td>
                    <td className="num">{fmtPct(m.within_7)}</td>
                    <td className="num">{fmtPct(m.at_risk_precision)}</td>
                    <td className="num">{fmtPct(m.at_risk_recall)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}
