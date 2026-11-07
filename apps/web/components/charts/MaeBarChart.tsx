"use client";
import { useState } from "react";
import type { EvalRow } from "@/lib/api";
import { fmt1, fmtNum, fmtPct, MODEL_LABELS } from "@/lib/format";
import { barPath, niceTicks, useWidth } from "./useWidth";

/**
 * MAE ανά μοντέλο — οριζόντιες μπάρες, μία σειρά.
 * Το τρέχον μοντέλο στο accent, τα υπόλοιπα σε de-emphasis γκρι. Τιμή στην άκρη κάθε μπάρας.
 */
export function MaeBarChart({ rows, current }: { rows: EvalRow[]; current: string }) {
  const { ref, width } = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<{ row: EvalRow; x: number; y: number } | null>(null);
  const data = [...rows].sort((a, b) => b.mae - a.mae);

  // Σε στενή οθόνη το όνομα πάει πάνω από τη μπάρα, ώστε να μην κόβεται.
  const stacked = width < 520;
  const labelW = stacked ? 0 : 180;
  const valueW = 48;
  const band = stacked ? 46 : 36;
  const barH = stacked ? 16 : 20;
  const barOffset = stacked ? 22 : (band - barH) / 2;
  const top = 8;
  const height = top + data.length * band + 24;
  const plotW = Math.max(60, width - labelW - valueW);
  const { max, ticks } = niceTicks(Math.max(...data.map((d) => d.mae)));
  const x = (v: number) => (v / max) * plotW;

  return (
    <div ref={ref} className="relative">
      <svg width={width} height={height} role="img" aria-label="Μέσο απόλυτο λάθος (μέρες) ανά μοντέλο">
        <g transform={`translate(${labelW},${top})`}>
          {ticks.map((t) => (
            <g key={t} transform={`translate(${x(t)},0)`}>
              <line y1={0} y2={data.length * band} stroke="var(--grid)" strokeWidth={1} />
              <text y={data.length * band + 16} textAnchor={t === 0 ? "start" : "middle"} fontSize={11} fill="var(--ink-muted)" className="tnum">
                {fmtNum(t)}
              </text>
            </g>
          ))}
          <line y1={0} y2={data.length * band} stroke="var(--axis)" strokeWidth={1} />
        </g>
        {data.map((d, i) => {
          const y = top + i * band + barOffset;
          const isCur = d.model === current;
          const w = Math.max(2, x(d.mae));
          return (
            <g
              key={d.model}
              tabIndex={0}
              onPointerMove={(e) => setHover({ row: d, x: e.nativeEvent.offsetX, y: top + i * band })}
              onPointerLeave={() => setHover(null)}
              onFocus={() => setHover({ row: d, x: labelW + w, y: top + i * band })}
              onBlur={() => setHover(null)}
              style={{ outline: "none" }}
            >
              <rect x={0} y={top + i * band} width={width} height={band} fill="transparent" />
              <text x={stacked ? 0 : labelW - 12} y={stacked ? top + i * band + 15 : y + barH / 2 + 4}
                textAnchor={stacked ? "start" : "end"} fontSize={13}
                fill={isCur ? "var(--ink)" : "var(--ink-2)"} fontWeight={isCur ? 600 : 400}>
                {MODEL_LABELS[d.model] ?? d.model}
              </text>
              <path className="grow-xb" style={{ animationDelay: `${i * 50}ms` }} d={barPath(labelW, y, w, barH, "right")}
                fill={isCur ? "var(--series-1)" : "var(--deemph)"}
                opacity={hover && hover.row.model !== d.model ? 0.6 : 1} />
              <text x={labelW + w + 6} y={y + barH / 2 + 4} fontSize={12} fill="var(--ink)" className="tnum"
                fontWeight={isCur ? 600 : 400}>
                {fmt1(d.mae)}
              </text>
            </g>
          );
        })}
      </svg>
      {hover && (
        <div className="viz-tooltip" style={{ left: Math.min(hover.x + 12, width - 200), top: hover.y - 8 }}>
          <div><strong>{fmt1(hover.row.mae)} μέρες</strong> MAE</div>
          <div>εντός ±3: {fmtPct(hover.row.within_3)} · ±7: {fmtPct(hover.row.within_7)}</div>
          <div className="text-ink-muted">{MODEL_LABELS[hover.row.model] ?? hover.row.model}</div>
        </div>
      )}
    </div>
  );
}
