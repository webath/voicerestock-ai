import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "VoiceRestock AI",
  description: "Προβλέψεις εξάντλησης αποθέματος και προτεινόμενες παραγγελίες για τον Account Manager",
};

// Πλοήγηση: οι σελίδες χωρίς owner ακόμα (Overview, At Risk, Orders, Voice) είναι του Νίκου.
const NAV = [
  { href: "/", label: "Overview" },
  { href: "/risk", label: "At Risk" },
  { href: "/orders", label: "Παραγγελίες" },
  { href: "/customers", label: "Πελάτες" },
  { href: "/evaluation", label: "Αξιολόγηση" },
  { href: "/voice", label: "Κλήσεις" },
];

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="el" className="h-full antialiased">
      <body className="flex min-h-full flex-col">
        <header className="border-b border-line bg-surface">
          <nav className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3 sm:px-6">
            <Link href="/" className="font-semibold text-ink">VoiceRestock AI</Link>
            <div className="flex flex-wrap gap-x-5 gap-y-1 text-sm text-ink-2">
              {NAV.map((n) => (
                <Link key={n.href} href={n.href} className="hover:text-ink">{n.label}</Link>
              ))}
            </div>
          </nav>
        </header>
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6">{children}</main>
      </body>
    </html>
  );
}
