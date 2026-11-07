"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { addDays, daysBetween, fmtDate, fmtMonth, fmtNum, unitLabel } from "@/lib/format";
import type { HistoryPoint } from "@/lib/types";

/**
 * Παραλαβές του πελάτη για ένα είδος, ανά εβδομάδα (μία σειρά → χωρίς legend· τον τίτλο τον δίνει η κάρτα).
 * Mark specs του dataviz skill: μπάρες ≤ 24px με στρογγυλεμένη άκρη 4px, γραμμές πλέγματος hairline,
 * tooltip ανά μπάρα με hit target όλη τη στήλη. Επιστροφές (πιστωτικά) κάτω από τη βάση, σε ουδέτερο χρώμα.
 */
const H = 230;
const PAD = { top: 18, right: 12, bottom: 28, left: 34 };

const mondayOf = (iso: string) => {
  const d = new Date(`${iso}T00:00:00Z`);
  const dow = (d.getUTCDay() + 6) % 7; // Δευτέρα = 0
  return addDays(iso, -dow);
};

function niceMax(v: number) {
  if (v <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  const n = v / p;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * p;
}

/** Μπάρα με στρογγυλεμένη ΜΟΝΟ την άκρη των δεδομένων (τετράγωνη στη βάση). */
function barPath(x: number, base: number, w: number, h: number) {
  const up = h >= 0;
  const a = Math.abs(h);
  const r = Math.min(4, w / 2, a);
  if (up) {
    const y = base - a;
    return `M${x},${base}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${base}Z`;
  }
  const y = base + a;
  return `M${x},${base}V${y - r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y - r}V${base}Z`;
}

export function PurchaseTimeline({
  points,
  unit,
  today,
  depletion,
  delivery,
}: {
  points: HistoryPoint[];
  unit: string;
  today: string;
  depletion: string | null;
  delivery?: string | null;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(300);
  const [hover, setHover] = useState<number | null>(null);
  const [asTable, setAsTable] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(280, Math.round(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const weeks = useMemo(() => {
    // 6 μήνες ιστορικό + 3 εβδομάδες μετά την πιο μακρινή ημερομηνία (σήμερα/εξάντληση), ώστε οι γραμμές να ξεχωρίζουν
    const end = mondayOf(addDays([today, depletion ?? today].sort().at(-1)!, 21));
    const start = mondayOf(addDays(today, -182));
    const byWeek = new Map<string, { qty: number; n: number }>();
    for (const p of points) {
      if (p.date < start) continue;
      const k = mondayOf(p.date);
      const w = byWeek.get(k) ?? { qty: 0, n: 0 };
      w.qty += p.qty;
      w.n += 1;
      byWeek.set(k, w);
    }
    const out: { week: string; qty: number; n: number }[] = [];
    for (let d = start; d <= end; d = addDays(d, 7)) out.push({ week: d, ...(byWeek.get(d) ?? { qty: 0, n: 0 }) });
    return out;
  }, [points, today, depletion]);

  const plotW = width - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;
  const band = plotW / weeks.length;
  const barW = Math.max(2, Math.min(24, band - 2)); // 2px κενό επιφάνειας ανάμεσα στις μπάρες
  const maxPos = niceMax(Math.max(1, ...weeks.map((w) => w.qty)));
  const minNeg = Math.min(0, ...weeks.map((w) => w.qty));
  const span = maxPos - minNeg;
  const y = (v: number) => PAD.top + ((maxPos - v) / span) * plotH;
  const base = y(0);
  const ticks = [0, maxPos / 2, maxPos].map((v) => Math.round(v * 10) / 10);
  const xOfDate = (iso: string) => PAD.left + (daysBetween(weeks[0].week, iso) / 7) * band;

  // Ετικέτα στην πρώτη εβδομάδα κάθε μήνα· παραλείπεται όταν θα «πατούσε» την προηγούμενη (< 34px).
  const monthTicks: { i: number; d: Date }[] = [];
  weeks.forEach((w, i) => {
    const d = new Date(`${w.week}T00:00:00Z`);
    const newMonth = i === 0 || d.getUTCMonth() !== new Date(`${weeks[i - 1].week}T00:00:00Z`).getUTCMonth();
    const prev = monthTicks.at(-1);
    if (newMonth && (!prev || (i - prev.i) * band >= 34)) monthTicks.push({ i, d });
  });
  const futureW = Math.max(0, width - PAD.right - xOfDate(today));

  const deliveries = points.filter((p) => p.date >= weeks[0].week).slice().reverse();
  const hv = hover != null ? weeks[hover] : null;

  return (
    // Το πλάτος μετριέται εδώ (πάντα ορατό, overflow-hidden) — όχι στο SVG, που αλλιώς «σπρώχνει» τη στήλη.
    <div ref={ref} className="w-full min-w-0 overflow-hidden">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-xs text-ink-2">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
          <span className="inline-flex items-center gap-1.5"><span aria-hidden className="h-3 w-0 border-l-2 border-dashed border-muted" /> Σήμερα ({fmtDate(today)})</span>
          {depletion && (
            <span className="inline-flex items-center gap-1.5"><span aria-hidden className="h-3 w-0 border-l-2 border-critical" /> Πρόβλεψη εξάντλησης ({fmtDate(depletion)})</span>
          )}
          {delivery && (
            <span className="inline-flex items-center gap-1.5"><span aria-hidden className="h-3 w-0 border-l-2 border-dotted border-ink-2" /> Προτεινόμενη παράδοση ({fmtDate(delivery)})</span>
          )}
        </div>
        <button className="rounded-md px-2 py-1 font-medium ring-1 ring-line hover:bg-surface-2" onClick={() => setAsTable((v) => !v)}>
          {asTable ? "Γράφημα" : "Πίνακας"}
        </button>
      </div>

      {asTable ? (
        <div className="max-h-64 overflow-auto rounded-lg ring-1 ring-line">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-surface text-left text-xs text-muted">
              <tr><th className="px-3 py-2">Ημερομηνία</th><th className="px-3 py-2 text-right">Καθαρή ποσότητα</th></tr>
            </thead>
            <tbody>
              {deliveries.map((p) => (
                <tr key={p.date} className="border-t border-line">
                  <td className="px-3 py-1.5 text-ink-2">{fmtDate(p.date)} {p.date.slice(0, 4)}</td>
                  <td className="tabular px-3 py-1.5 text-right text-ink">{p.qty} {unitLabel(unit, p.qty)}{p.qty < 0 && " (επιστροφή)"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="relative" onMouseLeave={() => setHover(null)}>
          <svg width={width} height={H} role="img" aria-label={`Παραλαβές ανά εβδομάδα, τελευταίοι 6 μήνες, σε ${unitLabel(unit)}`}>
            {ticks.map((t) => (
              <g key={t}>
                <line x1={PAD.left} x2={width - PAD.right} y1={y(t)} y2={y(t)} stroke="var(--grid)" strokeWidth={1} />
                <text x={PAD.left - 6} y={y(t) + 3.5} textAnchor="end" className="tabular" fontSize={10} fill="var(--muted)">{fmtNum(t)}</text>
              </g>
            ))}
            {/* ζώνη πρόβλεψης: από «σήμερα» και μετά δεν υπάρχουν ακόμα παραλαβές */}
            <rect x={xOfDate(today)} y={PAD.top - 6} width={futureW} height={base - PAD.top + 6} fill="var(--surface-2)" />
            {futureW >= 60 && (
              <text x={width - PAD.right - 4} y={PAD.top + 6} textAnchor="end" fontSize={10} fill="var(--muted)">πρόβλεψη</text>
            )}
            {weeks.map((w, i) =>
              w.qty === 0 ? null : (
                <path
                  key={w.week}
                  d={barPath(PAD.left + i * band + (band - barW) / 2, base, barW, base - y(w.qty))}
                  fill={w.qty < 0 ? "var(--axis)" : "var(--series-1)"}
                  opacity={hover == null || hover === i ? 1 : 0.45}
                />
              ),
            )}
            <line x1={PAD.left} x2={width - PAD.right} y1={base} y2={base} stroke="var(--axis)" strokeWidth={1} />
            {monthTicks.map(({ i, d }) => (
              <text key={i} x={PAD.left + i * band} y={H - 8} fontSize={10} fill="var(--muted)">
                {fmtMonth(d)}{d.getUTCMonth() === 0 ? ` ${d.getUTCFullYear()}` : ""}
              </text>
            ))}
            <line x1={xOfDate(today)} x2={xOfDate(today)} y1={PAD.top - 6} y2={base} stroke="var(--muted)" strokeWidth={1.5} strokeDasharray="3 3" />
            {delivery && <line x1={xOfDate(delivery)} x2={xOfDate(delivery)} y1={PAD.top - 6} y2={base} stroke="var(--ink-2)" strokeWidth={1.5} strokeDasharray="1 3" />}
            {depletion && <line x1={xOfDate(depletion)} x2={xOfDate(depletion)} y1={PAD.top - 6} y2={base} stroke="var(--critical)" strokeWidth={2} />}
            {/* hit targets: όλη η στήλη, όχι μόνο η μπάρα */}
            {weeks.map((w, i) => (
              <rect key={`hit-${w.week}`} x={PAD.left + i * band} y={PAD.top} width={band} height={plotH} fill="transparent" onMouseEnter={() => setHover(i)} />
            ))}
          </svg>
          {hv && (
            <div
              className="pointer-events-none absolute z-10 rounded-lg bg-surface px-3 py-2 text-xs shadow-lg ring-1 ring-line"
              style={{ left: Math.min(width - 190, Math.max(0, PAD.left + hover! * band - 60)), top: 0 }}
            >
              <div className="font-medium text-ink">Εβδομάδα {fmtDate(hv.week)} – {fmtDate(addDays(hv.week, 6))}</div>
              <div className="tabular mt-0.5 text-ink-2">
                {hv.n === 0 ? "Καμία παραλαβή" : `${hv.qty} ${unitLabel(unit, hv.qty)} · ${hv.n} ${hv.n === 1 ? "παραστατικό" : "παραστατικά"}`}
                {hv.qty < 0 && " (επιστροφή)"}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
