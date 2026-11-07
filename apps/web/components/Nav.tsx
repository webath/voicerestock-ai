"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { CommandPalette } from "./CommandPalette";
import { ThemeToggle } from "./ThemeToggle";

const NAV = [
  { href: "/", label: "Επισκόπηση" },
  { href: "/risk", label: "At Risk" },
  { href: "/orders", label: "Παραγγελίες" },
  { href: "/customers", label: "Πελάτες" },
  { href: "/voice", label: "Κλήσεις" },
  { href: "/evaluation", label: "Αξιολόγηση" },
];

export function Nav() {
  return <NavFrame path={usePathname()} />;
}

/** Ίδιο markup χωρίς ενεργό tab — fallback του Suspense στο prerender. */
export function NavFrame({ path }: { path: string | null }) {
  const active = (href: string) => path !== null && (href === "/" ? path === "/" : path.startsWith(href));
  return (
    <header className="glass-bar sticky top-0 z-30">
      <nav className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3 sm:px-6">
        <Link href="/" className="flex items-center gap-2.5 font-semibold tracking-tight text-ink">
          <Logo />
          <span title="Voice Ordering & Restock Assistant">VORA<span className="hidden text-ink-muted font-normal lg:inline"> · Voice Ordering & Restock Assistant</span></span>
        </Link>
        <div className="seg -mx-1 max-w-full overflow-x-auto">
          {NAV.map((n) => (
            <Link key={n.href} href={n.href} aria-current={active(n.href) ? "page" : undefined}>{n.label}</Link>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-2">
          <CommandPalette />
          <ThemeToggle />
        </div>
      </nav>
    </header>
  );
}

function Logo() {
  // Σταγόνα/μπουκάλι σε γυαλί — ο διανομέας νερών & ποτών.
  return (
    <svg width="26" height="26" viewBox="0 0 26 26" aria-hidden>
      <defs>
        <linearGradient id="lg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="var(--series-1)" stopOpacity="0.95" />
          <stop offset="1" stopColor="#1baf7a" stopOpacity="0.85" />
        </linearGradient>
      </defs>
      <rect x="1" y="1" width="24" height="24" rx="8" fill="url(#lg)" />
      <path d="M13 6.5c2.6 3.2 4.2 5.6 4.2 7.6a4.2 4.2 0 1 1-8.4 0c0-2 1.6-4.4 4.2-7.6z" fill="white" fillOpacity="0.92" />
      <path d="M11.2 14.6a1.9 1.9 0 0 0 1.9 1.9" stroke="url(#lg)" strokeWidth="1.4" strokeLinecap="round" fill="none" />
    </svg>
  );
}
