"use client";
import { useEffect, useRef, useState } from "react";

/** Πλάτος του container (για responsive SVG). */
export function useWidth<T extends HTMLElement>(initial = 320) {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(initial);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(280, Math.floor(e.contentRect.width))));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return { ref, width };
}

/** Bar με 4px στρογγυλεμένη άκρη δεδομένων και τετράγωνη βάση. */
export function barPath(x: number, y: number, w: number, h: number, dir: "up" | "down" | "right") {
  const r = Math.max(0, Math.min(4, (dir === "right" ? h : w) / 2, Math.abs(dir === "right" ? w : h)));
  if (dir === "right") {
    return `M${x},${y} h${w - r} a${r},${r} 0 0 1 ${r},${r} v${h - 2 * r} a${r},${r} 0 0 1 ${-r},${r} h${-(w - r)} z`;
  }
  if (dir === "up") {
    return `M${x},${y + h} v${-(h - r)} a${r},${r} 0 0 1 ${r},${-r} h${w - 2 * r} a${r},${r} 0 0 1 ${r},${r} v${h - r} z`;
  }
  return `M${x},${y} v${h - r} a${r},${r} 0 0 0 ${r},${r} h${w - 2 * r} a${r},${r} 0 0 0 ${r},${-r} v${-(h - r)} z`;
}

export function niceMax(v: number) {
  if (v <= 0) return 1;
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  const n = v / p;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * p;
}

/** Στρογγυλά ticks 0..max (βήμα 1/2/2,5/5 × 10^k, ~4–5 ticks). */
export function niceTicks(v: number, target = 4) {
  const raw = Math.max(v, 1e-9) / target;
  const p = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * p).find((s) => s >= raw)!;
  const max = Math.ceil(v / step) * step;
  return { max, ticks: Array.from({ length: Math.round(max / step) + 1 }, (_, i) => i * step) };
}
