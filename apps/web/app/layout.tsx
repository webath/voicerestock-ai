import type { Metadata } from "next";
import { Commissioner } from "next/font/google";
import Script from "next/script";
import { Suspense } from "react";
import { AssistantPanel } from "@/components/AssistantPanel";
import { Nav, NavFrame } from "@/components/Nav";
import { themeInitScript } from "@/components/ThemeToggle";
import { ToastProvider } from "@/components/Toast";
import "./globals.css";

const ui = Commissioner({ subsets: ["latin", "greek"], variable: "--font-ui", display: "swap" });

export const metadata: Metadata = {
  title: "VORA — Voice Ordering & Restock Assistant",
  description: "Προβλέψεις εξάντλησης αποθέματος και προτεινόμενες παραγγελίες για τον Account Manager",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="el" className={`${ui.variable} h-full antialiased`} suppressHydrationWarning>
      <body className="flex min-h-full flex-col">
        <Script id="vr-theme" strategy="beforeInteractive">{themeInitScript}</Script>
        <ToastProvider>
        <div className="backdrop" aria-hidden />
        <Suspense fallback={<NavFrame path={null} />}>
          <Nav />
        </Suspense>
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6">{children}</main>
        <footer className="mx-auto w-full max-w-6xl px-4 pb-8 text-xs text-ink-muted sm:px-6">
          DEMO ΔΙΑΝΟΜΕΣ Α.Ε. · συνθετικά δεδομένα · σενάριο «σήμερα 1/11/2026» · Revival Challenge #5
        </footer>
        <Suspense fallback={null}>
          <AssistantPanel />
        </Suspense>
        </ToastProvider>
      </body>
    </html>
  );
}
