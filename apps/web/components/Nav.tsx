"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { CommandPalette } from "./CommandPalette";
import { ThemeToggle } from "./ThemeToggle";

const NAV = [
  { href: "/", label: "Επισκόπηση" },
  { href: "/agent", label: "Agent" },
  { href: "/risk", label: "At Risk" },
  { href: "/orders", label: "Παραγγελίες" },
  { href: "/customers", label: "Πελάτες" },
  { href: "/voice", label: "Κλήσεις" },
  { href: "/campaigns", label: "Campaigns" },
  { href: "/market", label: "Market Scan" },
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
        <Link href="/" className="flex items-center gap-3 tracking-tight" title="Voice Ordering & Restock Assistant">
          <span className="vora-mark"><span className="vora-word" data-text="VORA">VORA</span></span>
          <span className="hidden text-ink-muted lg:inline">Voice Ordering & Restock Assistant</span>
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

