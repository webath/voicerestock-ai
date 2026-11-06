"use client";
import Link from "next/link";
import { useMemo, useState } from "react";
import { ErrorBox, Loading, PageHeader, UrgencyBadge } from "@/components/ui";
import { useApi, type Customer, type Suggestion } from "@/lib/api";
import { fmtDay, fmtNum } from "@/lib/format";

// Owner: Δημήτρης. Λίστα πελατών → σελίδα πελάτη.
export default function CustomersPage() {
  const customers = useApi<Customer[]>("/api/customers");
  const suggestions = useApi<Suggestion[]>("/api/suggestions");
  const [q, setQ] = useState("");

  const rows = useMemo(() => {
    const byTrdr = new Map((suggestions.data ?? []).map((s) => [s.TRDR, s]));
    const needle = q.trim().toLowerCase();
    return (customers.data ?? [])
      .filter((c) => !needle || `${c.NAME} ${c.CODE} ${c.CITY} ${c.AREA} ${c.SALESMAN_NAME}`.toLowerCase().includes(needle))
      .map((c) => ({ c, s: byTrdr.get(c.TRDR) }))
      .sort((a, b) => (a.s?.LINES[0].PREDICTED_DEPLETION_DATE ?? "9").localeCompare(b.s?.LINES[0].PREDICTED_DEPLETION_DATE ?? "9"));
  }, [customers.data, suggestions.data, q]);

  if (customers.error) return <ErrorBox message={customers.error} />;
  if (!customers.data) return <Loading />;

  return (
    <>
      <PageHeader title="Πελάτες" subtitle={`${fmtNum(customers.data.length)} πελάτες · ταξινόμηση κατά πρώτη εκτιμώμενη εξάντληση`}>
        <input
          type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Αναζήτηση πελάτη, πόλης, πωλητή"
          className="field w-72 max-w-full"
          aria-label="Αναζήτηση πελάτη"
        />
      </PageHeader>
      <div className="card fade-in overflow-x-auto">
        <table className="data">
          <thead>
            <tr>
              <th>Πελάτης</th>
              <th>Τύπος / Περιοχή</th>
              <th>Πωλητής</th>
              <th>Πρώτη εξάντληση</th>
              <th className="num">Είδη στην πρόταση</th>
              <th>Επείγον</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ c, s }) => (
              <tr key={c.TRDR}>
                <td>
                  <Link href={`/customers/${c.TRDR}`} className="font-medium text-ink hover:underline">{c.NAME}</Link>
                  <div className="text-xs text-ink-muted">{c.CODE}{c.cold_start ? " · νέος πελάτης" : ""}</div>
                </td>
                <td className="text-ink-2">{c.TRDCATEGORY}<div className="text-xs text-ink-muted">{c.CITY}, {c.AREA}</div></td>
                <td className="text-ink-2">{c.SALESMAN_NAME}</td>
                <td className="tnum">{s ? fmtDay(s.LINES[0].PREDICTED_DEPLETION_DATE) : "–"}</td>
                <td className="num">{s ? s.LINES.length : "–"}</td>
                <td>{s ? <UrgencyBadge urgency={s.urgency} /> : <UrgencyBadge urgency="none" />}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
