"use client";

import { useEffect, useMemo, useState } from "react";
import { salesmanQuery, useSalesman } from "@/components/salesman";
import { SuggestionCard } from "@/components/suggestion-card";
import { Empty, ErrorBox, PageHeader, Skeleton } from "@/components/ui";
import { useApi } from "@/lib/api";
import { OPEN_STATUSES, URGENCY } from "@/lib/format";
import type { Suggestion } from "@/lib/types";

type Tab = "open" | "drafts" | "all";
const TABS: { key: Tab; label: string }[] = [
  { key: "open", label: "Ανοιχτές" },
  { key: "drafts", label: "Drafts στο ERP" },
  { key: "all", label: "Όλες" },
];

export default function OrdersView() {
  const { salesman, name } = useSalesman();
  const { data, error, reload } = useApi<Suggestion[]>(`/suggestions${salesmanQuery(salesman)}`, { refreshMs: 10_000 });
  const [local, setLocal] = useState<Record<string, Suggestion>>({});
  const [tab, setTab] = useState<Tab>("open");

  // Οι αλλαγές από τις κάρτες φαίνονται αμέσως· όταν έρθει νεότερη έκδοση από το polling, κερδίζει αυτή.
  const merged = useMemo(
    () =>
      (data ?? []).map((s) => {
        const l = local[s.id];
        return l && (l.version > s.version || (l.version === s.version && l.status !== s.status && l.updated_at >= s.updated_at)) ? l : s;
      }),
    [data, local],
  );
  const list = useMemo(() => {
    return merged
      .filter((s) => (tab === "open" ? OPEN_STATUSES.includes(s.status) || s.status === "posting" : tab === "drafts" ? s.status === "draft_created" : true))
      .sort((a, b) => URGENCY[a.urgency].rank - URGENCY[b.urgency].rank || a.SUGGESTED_DELIVERY_DATE.localeCompare(b.SUGGESTED_DELIVERY_DATE));
  }, [merged, tab]);

  // Άνοιγμα από link «/orders#SUG-…»: αν η πρόταση δεν είναι στις ανοιχτές, δείξε όλες.
  useEffect(() => {
    const id = window.location.hash.slice(1);
    if (!id || !data) return;
    const s = data.find((x) => x.id === id);
    // eslint-disable-next-line react-hooks/set-state-in-effect -- μία φορά, από το hash του URL
    if (s && !OPEN_STATUSES.includes(s.status)) setTab("all");
    requestAnimationFrame(() => document.getElementById(id)?.scrollIntoView({ block: "start" }));
  }, [data]);

  const counts = useMemo(
    () => ({
      open: merged.filter((s) => OPEN_STATUSES.includes(s.status)).length,
      drafts: merged.filter((s) => s.status === "draft_created").length,
      all: merged.length,
    }),
    [merged],
  );

  return (
    <>
      <PageHeader
        title="Προτάσεις παραγγελίας"
        subtitle={
          <>
            Μία πρόταση ανά πελάτη, από το μοντέλο πρόβλεψης. Αλλάξτε ποσότητες και εγκρίνετε· στο ERP μπαίνει πάντα <b className="font-medium text-ink">draft</b>
            {salesman != null && <> · πωλητής <b className="font-medium text-ink">{name(salesman)}</b></>}.
          </>
        }
      />
      <div className="mb-4 inline-flex rounded-lg bg-surface p-1 ring-1 ring-line" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.key}
            role="tab"
            aria-selected={tab === t.key}
            onClick={() => setTab(t.key)}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${tab === t.key ? "bg-ink text-page" : "text-ink-2 hover:text-ink"}`}
          >
            {t.label} <span className="tabular opacity-70">{data ? counts[t.key] : ""}</span>
          </button>
        ))}
      </div>

      {error && <div className="mb-4"><ErrorBox error={error} onRetry={reload} /></div>}
      {!data ? (
        <div className="space-y-4"><Skeleton className="h-56" /><Skeleton className="h-56" /></div>
      ) : list.length === 0 ? (
        <div className="rounded-xl bg-surface ring-1 ring-line"><Empty>Καμία πρόταση σε αυτή την καρτέλα.</Empty></div>
      ) : (
        <div className="grid gap-4 xl:grid-cols-2">
          {list.map((s) => (
            <SuggestionCard key={s.id} s={s} onChange={(n) => setLocal((m) => ({ ...m, [n.id]: n }))} />
          ))}
        </div>
      )}
    </>
  );
}
