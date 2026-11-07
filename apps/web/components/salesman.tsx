"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useApi } from "@/lib/api";
import type { Salesman } from "@/lib/types";

/** Ο πωλητής που «βλέπει» το dashboard (ή όλοι). Κρατιέται στον browser για ευκολία — όχι κρίσιμη κατάσταση. */
interface Ctx {
  salesman: number | null;
  setSalesman: (s: number | null) => void;
  salesmen: Salesman[];
  name: (id: number | null | undefined) => string;
}

const SalesmanContext = createContext<Ctx>({ salesman: null, setSalesman: () => {}, salesmen: [], name: () => "" });
const KEY = "vr.salesman";

export function SalesmanProvider({ children }: { children: ReactNode }) {
  const [salesman, setState] = useState<number | null>(null);
  const { data } = useApi<Salesman[]>("/salesmen", { refreshMs: 60_000 });
  const salesmen = useMemo(() => data ?? [], [data]);

  useEffect(() => {
    try {
      const v = window.localStorage.getItem(KEY);
      // eslint-disable-next-line react-hooks/set-state-in-effect -- μία φορά, από αποθηκευμένη προτίμηση
      if (v) setState(Number(v));
    } catch {
      /* ιδιωτική περιήγηση κ.λπ. */
    }
  }, []);

  const setSalesman = useCallback((s: number | null) => {
    setState(s);
    try {
      if (s == null) window.localStorage.removeItem(KEY);
      else window.localStorage.setItem(KEY, String(s));
    } catch {
      /* αγνόησε */
    }
  }, []);

  const name = useCallback(
    (id: number | null | undefined) => salesmen.find((s) => s.PRSN === id)?.NAME ?? (id == null ? "" : `#${id}`),
    [salesmen],
  );

  return <SalesmanContext.Provider value={{ salesman, setSalesman, salesmen, name }}>{children}</SalesmanContext.Provider>;
}

export const useSalesman = () => useContext(SalesmanContext);

/** «?salesman=105» ή κενό για όλους. */
export const salesmanQuery = (s: number | null, prefix = "?") => (s == null ? "" : `${prefix}salesman=${s}`);
