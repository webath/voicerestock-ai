"use client";
import { useState } from "react";
import { fmtDayLong, fmtNum } from "@/lib/format";
import { barPath, niceTicks, useWidth } from "./useWidth";

/** Στήλες ανά μέρα (μία σειρά): πόσα ζεύγη πελάτη × είδους εξαντλούνται εκείνη τη μέρα. */
export function DayColumns({ days }: { days: { date: string; count: number }[] }) {
  const { ref, width } = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const left = 32, right = 4, top = 18, bottom = 26, height = 200;
  const plotW = width - left - right, plotH = height - top - bottom;
  const { max, ticks } = niceTicks(Math.max(1, ...days.map((d) => d.count)), 3);
  const band = plotW / Math.max(1, days.length);
  const barW = Math.min(24, band - 4);
  const y = (v: number) => top + plotH - (v / max) * plotH;
  const peak = days.reduce((a, d, i) => (d.count > days[a].count ? i : a), 0);

  return (
    <div ref={ref} className="relative">
      <svg width={width} height={height} role="img" aria-label="Εξαντλήσεις ανά μέρα, επόμενες 14 μέρες">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={left} x2={width - right} y1={y(t)} y2={y(t)} stroke={t === 0 ? "var(--axis)" : "var(--grid)"} />
            <text x={left - 6} y={y(t) + 4} textAnchor="end" fontSize={11} fill="var(--ink-muted)" className="tnum">{fmtNum(t)}</text>
          </g>
        ))}
        {days.map((d, i) => {
          const cx = left + band * i + band / 2;
          const h = Math.max(0, y(0) - y(d.count));
          const wd = new Date(d.date + "T00:00:00Z");
          return (
            <g key={d.date} onPointerEnter={() => setHover(i)} onPointerLeave={() => setHover(null)}
              tabIndex={0} onFocus={() => setHover(i)} onBlur={() => setHover(null)} style={{ outline: "none" }}>
              <rect x={cx - band / 2} y={top} width={band} height={plotH + bottom} fill="transparent" />
              {d.count > 0 && (
                <path className="grow-y" style={{ animationDelay: `${i * 30}ms` }}
                  d={barPath(cx - barW / 2, y(d.count), barW, h, "up")}
                  fill="var(--series-1)" opacity={hover !== null && hover !== i ? 0.5 : 1} />
              )}
              {i === peak && d.count > 0 && (
                <text x={cx} y={y(d.count) - 6} textAnchor="middle" fontSize={11} fontWeight={600} fill="var(--ink)" className="tnum">{fmtNum(d.count)}</text>
              )}
              <text x={cx} y={height - 8} textAnchor="middle" fontSize={11}
                fill={wd.getUTCDay() === 0 ? "var(--ink-muted)" : "var(--ink-2)"} className="tnum">{wd.getUTCDate()}</text>
            </g>
          );
        })}
      </svg>
      {hover !== null && (
        <div className="viz-tooltip" style={{ left: Math.min(left + band * hover + band / 2 + 8, width - 170), top: 0 }}>
          <div><strong>{fmtNum(days[hover].count)}</strong> είδη τελειώνουν</div>
          <div className="text-ink-muted">{fmtDayLong(days[hover].date)}</div>
        </div>
      )}
    </div>
  );
}
