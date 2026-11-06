"use client";
import { useMemo, useState } from "react";
import { CUTOFF, fmtDay, fmtDayLong, fmtNum } from "@/lib/format";
import { barPath, niceTicks, useWidth } from "./useWidth";

const DAY = 86_400_000;
const t = (iso: string) => Date.parse(iso + "T00:00:00Z");

/**
 * Παραλαβές ενός είδους (στήλες ανά μέρα, πιστωτικά προς τα κάτω) + «σήμερα» + εκτιμώμενη εξάντληση.
 * Η περιοχή cutoff → εξάντληση είναι το εκτιμώμενο απόθεμα (wash 10%).
 */
export function PurchaseTimeline({ points, unit, depletion, delivery, daysBack = 150 }: {
  points: { date: string; qty: number }[];
  unit: string;
  depletion: string | null;
  delivery?: string | null;
  daysBack?: number;
}) {
  const { ref, width } = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<{ date: string; qty: number; x: number; y: number } | null>(null);

  const cut = t(CUTOFF);
  const start = cut - daysBack * DAY;
  const endDay = Math.max(cut + 21 * DAY, (depletion ? t(depletion) : cut) + 7 * DAY);
  const pts = useMemo(() => points.filter((p) => t(p.date) > start), [points, start]);

  const left = 36, right = 12, top = 28, bottom = 28;
  const height = 240;
  const plotW = width - left - right;
  const plotH = height - top - bottom;
  const { max: maxQ, ticks: yTicks } = niceTicks(Math.max(1, ...pts.map((p) => p.qty)), 3);
  const minQ = Math.min(0, ...pts.map((p) => p.qty));
  const span = endDay - start;
  const xs = (ms: number) => left + ((ms - start) / span) * plotW;
  const ys = (q: number) => top + ((maxQ - q) / (maxQ - minQ)) * plotH;
  const barW = Math.max(2, Math.min(24, (plotW / (span / DAY)) * 0.9));

  // μηνιαία ticks στον άξονα X
  const months: number[] = [];
  const d0 = new Date(start);
  for (let m = new Date(Date.UTC(d0.getUTCFullYear(), d0.getUTCMonth() + 1, 1)); m.getTime() < endDay; m.setUTCMonth(m.getUTCMonth() + 1)) {
    months.push(m.getTime());
  }

  const xCut = xs(cut);
  const xDep = depletion ? xs(t(depletion)) : null;
  const xDel = delivery ? xs(t(delivery)) : null;

  return (
    <div ref={ref} className="relative">
      <svg width={width} height={height} role="img"
        aria-label={`Παραλαβές ανά μέρα (${unit}) και εκτιμώμενη εξάντληση ${depletion ?? "καμία σε 90 μέρες"}`}>
        {/* εκτιμώμενο απόθεμα: σήμερα → εξάντληση */}
        {xDep !== null && <rect x={xCut} y={top} width={Math.max(0, xDep - xCut)} height={plotH} fill="var(--series-1-wash)" />}
        {/* grid + y ticks */}
        {yTicks.map((q) => (
          <g key={q}>
            <line x1={left} x2={width - right} y1={ys(q)} y2={ys(q)} stroke={q === 0 ? "var(--axis)" : "var(--grid)"} strokeWidth={1} />
            <text x={left - 6} y={ys(q) + 4} textAnchor="end" fontSize={11} fill="var(--ink-muted)" className="tnum">{fmtNum(q)}</text>
          </g>
        ))}
        {months.map((m) => (
          <text key={m} x={xs(m)} y={height - 8} textAnchor="middle" fontSize={11} fill="var(--ink-muted)">
            {new Intl.DateTimeFormat("el-GR", { month: "short", timeZone: "UTC" }).format(new Date(m))}
          </text>
        ))}
        {/* στήλες */}
        {pts.map((p) => {
          const cx = xs(t(p.date));
          const up = p.qty >= 0;
          const y = up ? ys(p.qty) : ys(0);
          const h = Math.max(1, Math.abs(ys(p.qty) - ys(0)));
          return (
            <g key={p.date}
              onPointerMove={() => setHover({ ...p, x: cx, y })}
              onPointerLeave={() => setHover(null)}>
              <rect x={cx - Math.max(6, barW)} y={top} width={Math.max(12, barW * 2)} height={plotH} fill="transparent" />
              <path className="grow-y" d={barPath(cx - barW / 2, y, barW, h, up ? "up" : "down")}
                fill={up ? "var(--series-1)" : "var(--ink-muted)"}
                opacity={hover && hover.date !== p.date ? 0.55 : 1} />
            </g>
          );
        })}
        {/* σήμερα */}
        <line x1={xCut} x2={xCut} y1={top} y2={top + plotH} stroke="var(--ink-muted)" strokeWidth={1} />
        {/* παράδοση */}
        {xDel !== null && (
          <g>
            <line x1={xDel} x2={xDel} y1={top} y2={top + plotH} stroke="var(--series-1)" strokeWidth={2} />
            <circle cx={xDel} cy={top + plotH} r={4} fill="var(--series-1)" stroke="var(--surface)" strokeWidth={2} />
          </g>
        )}
        {/* εξάντληση */}
        {xDep !== null && (
          <g>
            <line x1={xDep} x2={xDep} y1={top - 6} y2={top + plotH} stroke="var(--ink)" strokeWidth={2} />
            <text x={Math.min(xDep + 4, width - right)} y={top - 10} fontSize={11} fill="var(--ink)" fontWeight={600}
              textAnchor={xDep + 120 > width ? "end" : "start"}>
              εξάντληση {fmtDay(depletion)}
            </text>
          </g>
        )}
      </svg>
      {hover && (
        <div className="viz-tooltip" style={{ left: Math.min(hover.x + 10, width - 160), top: Math.max(0, hover.y - 44) }}>
          <div><strong>{fmtNum(Math.abs(hover.qty))} {unit}</strong> {hover.qty < 0 ? "επιστροφή" : "παραλαβή"}</div>
          <div className="text-ink-muted">{fmtDayLong(hover.date)}</div>
        </div>
      )}
      <div className="mt-2 flex flex-wrap gap-4 text-xs text-ink-2">
        <span className="inline-flex items-center gap-1.5"><span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: "var(--series-1)" }} />Παραλαβή</span>
        <span className="inline-flex items-center gap-1.5"><span className="inline-block h-3 w-px" style={{ background: "var(--ink-muted)" }} />Cutoff {fmtDay(CUTOFF)}</span>
        <span className="inline-flex items-center gap-1.5"><span className="inline-block h-2.5 w-4" style={{ background: "var(--series-1-wash)", border: "1px solid var(--border)" }} />Εκτιμώμενο απόθεμα</span>
        {xDel !== null && <span className="inline-flex items-center gap-1.5"><span className="inline-block h-3 w-0.5" style={{ background: "var(--series-1)" }} />Προτεινόμενη παράδοση {fmtDay(delivery)}</span>}
        <span className="inline-flex items-center gap-1.5"><span className="inline-block h-3 w-0.5" style={{ background: "var(--ink)" }} />Εκτιμώμενη εξάντληση</span>
      </div>
    </div>
  );
}
