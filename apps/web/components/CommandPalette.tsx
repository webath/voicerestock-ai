"use client";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { apiGet, type Customer } from "@/lib/api";

const PAGES = [
  { href: "/", label: "Επισκόπηση" },
  { href: "/risk", label: "At Risk" },
  { href: "/orders", label: "Παραγγελίες" },
  { href: "/customers", label: "Πελάτες" },
  { href: "/voice", label: "Κλήσεις" },
  { href: "/evaluation", label: "Αξιολόγηση" },
];

// Αναζήτηση χωρίς τόνους/κεφαλαία: «οικονομικο» βρίσκει «Οικονομικό».
const norm = (s: string) => s.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();

/** ⌘K / Ctrl+K: γρήγορη μετάβαση σε πελάτη ή σελίδα. */
export function CommandPalette() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setOpen((o) => !o); }
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (!open) return;
    input.current?.focus();
    if (customers.length === 0) apiGet<Customer[]>("/api/customers").then(setCustomers).catch(() => {});
  }, [open, customers.length]);

  const results = useMemo(() => {
    const n = norm(q.trim());
    const pages = PAGES.filter((p) => !n || norm(p.label).includes(n)).map((p) => ({ href: p.href, title: p.label, sub: "Σελίδα" }));
    const cs = customers
      .filter((c) => n && norm(`${c.NAME} ${c.CODE} ${c.CITY} ${c.AREA}`).includes(n))
      .slice(0, 8)
      .map((c) => ({ href: `/customers/${c.TRDR}`, title: c.NAME, sub: `${c.TRDCATEGORY} · ${c.CITY} · ${c.CODE}` }));
    return [...cs, ...pages].slice(0, 12);
  }, [q, customers]);

  const go = (href: string) => { setOpen(false); setQ(""); router.push(href); };

  return (
    <>
      <button type="button" onClick={() => setOpen(true)} className="btn btn-ghost btn-sm !h-9 gap-2 text-ink-2" aria-label="Αναζήτηση (⌘K)">
        <span aria-hidden>⌕</span>
        <span className="hidden text-xs sm:inline">Αναζήτηση</span>
        <kbd className="hidden rounded border border-line px-1 text-[10px] text-ink-muted sm:inline">⌘K</kbd>
      </button>
      {open && (
        <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/35 px-4 pt-[12vh] backdrop-blur-[3px]" onClick={() => setOpen(false)}>
          <div className="card palette w-full max-w-lg !rounded-2xl" role="dialog" aria-modal="true" aria-label="Αναζήτηση" onClick={(e) => e.stopPropagation()}>
            <input
              ref={input} value={q} placeholder="Πελάτης, πόλη, κωδικός ή σελίδα…" aria-label="Αναζήτηση"
              className="w-full rounded-t-2xl border-b border-[var(--grid)] bg-transparent px-4 py-3.5 text-base text-ink outline-none placeholder:text-ink-muted"
              onChange={(e) => { setQ(e.target.value); setSel(0); }}
              onKeyDown={(e) => {
                if (e.key === "ArrowDown") { e.preventDefault(); setSel((i) => Math.min(i + 1, results.length - 1)); }
                if (e.key === "ArrowUp") { e.preventDefault(); setSel((i) => Math.max(i - 1, 0)); }
                if (e.key === "Enter" && results[sel]) go(results[sel].href);
              }}
            />
            <ul className="max-h-80 overflow-y-auto p-1.5" role="listbox">
              {results.length === 0 && <li className="px-3 py-6 text-center text-sm text-ink-muted">Τίποτα — δοκίμασε άλλο όνομα ή πόλη.</li>}
              {results.map((r, i) => (
                <li key={r.href} role="option" aria-selected={i === sel}>
                  <button type="button" onMouseEnter={() => setSel(i)} onClick={() => go(r.href)}
                    className="flex w-full items-center justify-between gap-3 rounded-xl px-3 py-2 text-left transition-colors"
                    style={{ background: i === sel ? "var(--series-1-wash)" : "transparent" }}>
                    <span className="min-w-0"><span className="block truncate text-sm font-medium text-ink">{r.title}</span>
                      <span className="block truncate text-xs text-ink-muted">{r.sub}</span></span>
                    {i === sel && <span aria-hidden className="text-xs text-ink-muted">↵</span>}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </>
  );
}
