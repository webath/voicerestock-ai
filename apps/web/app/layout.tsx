import type { Metadata } from "next";
import { Suspense } from "react";
import { SalesmanProvider } from "@/components/salesman";
import { Brand, Nav, TopBar } from "@/components/shell";
import { SCENARIO_TODAY, fmtDateLong } from "@/lib/format";
import "./globals.css";

export const metadata: Metadata = {
  title: "VoiceRestock AI",
  description: "Προβλέψεις εξάντλησης αποθέματος, προτάσεις αναπαραγγελίας και φωνητική επιβεβαίωση — DEMO ΔΙΑΝΟΜΕΣ Α.Ε.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="el" className="h-full antialiased">
      <body className="min-h-full">
        <SalesmanProvider>
          <div className="md:grid md:min-h-screen md:grid-cols-[240px_1fr]">
            <aside className="flex flex-col gap-3 border-b border-line px-4 py-3 md:sticky md:top-0 md:h-screen md:items-stretch md:border-r md:border-b-0 md:px-4 md:py-6">
              <Brand />
              <div className="-mx-4 overflow-x-auto px-4 md:mx-0 md:overflow-visible md:px-0">
                <Suspense fallback={null}>
                  <Nav />
                </Suspense>
              </div>
              <p className="mt-auto hidden px-1 text-xs leading-relaxed text-muted md:block">
                Ημερομηνία σεναρίου:
                <br />
                <span className="text-ink-2">{fmtDateLong(SCENARIO_TODAY)} 2026</span>
                <br />
                Ιστορικό ERP έως 31/10/2026.
              </p>
            </aside>
            <div className="min-w-0">
              <TopBar />
              <main className="mx-auto w-full max-w-7xl px-4 py-6 md:px-8">{children}</main>
            </div>
          </div>
        </SalesmanProvider>
      </body>
    </html>
  );
}
