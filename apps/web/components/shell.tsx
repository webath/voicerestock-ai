"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useApi, voice } from "@/lib/api";
import type { VoiceHealth } from "@/lib/types";
import { useSalesman } from "./salesman";

const NAV = [
  { href: "/", label: "Επισκόπηση", icon: "◧" },
  { href: "/risk", label: "At Risk", icon: "▲" },
  { href: "/orders", label: "Προτάσεις παραγγελίας", icon: "☰" },
  { href: "/voice", label: "Κλήσεις", icon: "☏" },
  { href: "/evaluation", label: "Αξιολόγηση μοντέλου", icon: "◔" },
];

function Health() {
  const app = useApi<{ ok: boolean; mock?: boolean }>("/health", { refreshMs: 15_000 });
  const vh = useApi<VoiceHealth>("/health", { refreshMs: 15_000, client: voice });
  const item = (ok: boolean | undefined, label: string, extra?: string) => (
    <span className="inline-flex items-center gap-1.5" title={ok ? `${label}: συνδεδεμένο` : `${label}: χωρίς σύνδεση`}>
      <span aria-hidden className={`size-2 rounded-full ${ok ? "bg-good" : ok === false ? "bg-critical" : "bg-muted"}`} />
      <span className="text-ink-2">
        {label}
        {extra && <span className="text-muted"> · {extra}</span>}
        {ok === false && <span className="text-critical"> · εκτός</span>}
      </span>
    </span>
  );
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
      {item(app.error ? false : app.data?.ok, "App API", app.data?.mock ? "mock" : undefined)}
      {item(vh.error ? false : vh.data?.ok, "Voice agent", vh.data?.active_calls.length ? `${vh.data.active_calls.length} κλήση` : undefined)}
    </div>
  );
}

export function Nav() {
  const path = usePathname();
  const active = (href: string) => (href === "/" ? path === "/" : path.startsWith(href) || (href === "/risk" && path.startsWith("/customers")));
  return (
    <nav className="flex w-max gap-1 md:w-auto md:flex-col" aria-label="Κύριο μενού">
      {NAV.map((n) => (
        <Link
          key={n.href}
          href={n.href}
          aria-current={active(n.href) ? "page" : undefined}
          className={`flex shrink-0 items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition ${
            active(n.href) ? "bg-surface text-ink ring-1 ring-line" : "text-ink-2 hover:bg-surface hover:text-ink"
          }`}
        >
          <span aria-hidden className="w-4 text-center text-muted">{n.icon}</span>
          {n.label}
        </Link>
      ))}
    </nav>
  );
}

export function TopBar() {
  const { salesman, setSalesman, salesmen } = useSalesman();
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line bg-page/90 px-4 py-3 backdrop-blur md:px-8">
      <label className="flex items-center gap-2 text-sm">
        <span className="text-ink-2">Πωλητής</span>
        <select
          value={salesman ?? ""}
          onChange={(e) => setSalesman(e.target.value ? Number(e.target.value) : null)}
          className="rounded-lg bg-surface px-2.5 py-1.5 text-sm text-ink ring-1 ring-line outline-none focus:ring-2 focus:ring-series"
        >
          <option value="">Όλοι οι πωλητές</option>
          {salesmen.map((s) => (
            <option key={s.PRSN} value={s.PRSN}>
              {s.NAME}
            </option>
          ))}
        </select>
      </label>
      <Health />
    </div>
  );
}

export function Brand() {
  return (
    <Link href="/" className="mb-0 flex items-center gap-2.5 px-1 md:mb-6">
      <span aria-hidden className="grid size-8 place-items-center rounded-lg bg-ink text-sm font-bold text-page">VR</span>
      <span className="leading-tight">
        <span className="block text-sm font-semibold text-ink">VoiceRestock AI</span>
        <span className="block text-xs text-muted">DEMO ΔΙΑΝΟΜΕΣ Α.Ε.</span>
      </span>
    </Link>
  );
}
