"use client";

import { useState } from "react";
import { fmtNum, fmtPct } from "@/lib/format";
import type { EvaluationRow } from "@/lib/types";

/**
 * MAE ανά μοντέλο (μικρότερο = καλύτερο). Οριζόντιες μπάρες, μία σειρά/ένα χρώμα, τιμή δίπλα στην άκρη
 * σε χρώμα κειμένου (όχι της σειράς), tooltip με όλους τους δείκτες. Η σειρά ακολουθεί το API.
 */
export function MaeBars({ rows }: { rows: EvaluationRow[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const data = rows.filter((r) => r.mae != null);
  const max = Math.max(1, ...data.map((r) => r.mae!));
  const best = Math.min(...data.map((r) => r.mae!));

  return (
    <div role="img" aria-label="Μέσο απόλυτο σφάλμα (ημέρες) ανά μοντέλο" className="space-y-2.5">
      {data.map((r, i) => (
        <div
          key={r.model}
          className="relative grid grid-cols-[minmax(110px,180px)_1fr] items-center gap-3 rounded-md py-0.5"
          onMouseEnter={() => setHover(i)}
          onMouseLeave={() => setHover(null)}
        >
          <div className="truncate text-right text-xs text-ink-2" title={r.model}>
            {r.model}
          </div>
          <div className="flex items-center gap-2">
            <div
              className="h-5 rounded-r-[4px] bg-series transition-opacity"
              style={{ width: `${Math.max(1, (r.mae! / max) * 100) * 0.85}%`, opacity: hover == null || hover === i ? 1 : 0.45 }}
            />
            <span className="tabular whitespace-nowrap text-xs font-medium text-ink">
              {fmtNum(r.mae)} ημ.{r.mae === best && <span className="ml-1 text-good-ink">✓ καλύτερο</span>}
            </span>
          </div>
          {hover === i && (
            <div className="pointer-events-none absolute left-[190px] top-7 z-10 rounded-lg bg-surface px-3 py-2 text-xs shadow-lg ring-1 ring-line">
              <div className="font-medium text-ink">{r.model}</div>
              <div className="tabular mt-1 grid grid-cols-2 gap-x-4 gap-y-0.5 text-ink-2">
                <span>MAE</span><span className="text-right text-ink">{fmtNum(r.mae)} ημ.</span>
                <span>εντός ±3</span><span className="text-right text-ink">{fmtPct(r.within_3)}</span>
                <span>εντός ±7</span><span className="text-right text-ink">{fmtPct(r.within_7)}</span>
                <span>At Risk P / R</span><span className="text-right text-ink">{fmtPct(r.at_risk_precision)} / {fmtPct(r.at_risk_recall)}</span>
              </div>
            </div>
          )}
        </div>
      ))}
      <div className="grid grid-cols-[minmax(110px,180px)_1fr] gap-3 pt-1 text-xs text-muted">
        <span />
        <span>Μέσο σφάλμα σε ημέρες · μικρότερο = καλύτερο</span>
      </div>
    </div>
  );
}
