import Link from "next/link";
import { PageHeader } from "@/components/ui";

// Προσωρινό Overview — το αντικαθιστά ο Νίκος (docs/PLAN.md, Φάση 3).
export default function Home() {
  const links = [
    { href: "/customers", title: "Πελάτες", text: "Ιστορικό αγορών, πρόβλεψη εξάντλησης ανά είδος και προτεινόμενη παραγγελία." },
    { href: "/evaluation", title: "Αξιολόγηση", text: "Ακρίβεια του μοντέλου στο backtest σε σύγκριση με το baseline." },
  ];
  return (
    <>
      <PageHeader title="VoiceRestock AI" subtitle="Από τα τιμολόγια του ERP σε έγκαιρες, εξηγήσιμες προτάσεις αναπαραγγελίας." />
      <div className="grid gap-4 sm:grid-cols-2">
        {links.map((l) => (
          <Link key={l.href} href={l.href} className="card block p-5 hover:bg-surface-2">
            <div className="font-semibold text-ink">{l.title}</div>
            <p className="mt-1 text-sm text-ink-2">{l.text}</p>
          </Link>
        ))}
      </div>
    </>
  );
}
