"use client";
import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

type Kind = "success" | "error" | "info";
interface Toast { id: number; kind: Kind; title: string; text?: string }

const Ctx = createContext<(t: Omit<Toast, "id">) => void>(() => {});
export const useToast = () => useContext(Ctx);

const ICON: Record<Kind, { icon: string; color: string }> = {
  success: { icon: "✓", color: "var(--good)" },
  error: { icon: "!", color: "var(--critical)" },
  info: { icon: "i", color: "var(--series-1)" },
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((t: Omit<Toast, "id">) => {
    const id = Date.now() + Math.random();
    setToasts((xs) => [...xs.slice(-3), { ...t, id }]);
    setTimeout(() => setToasts((xs) => xs.filter((x) => x.id !== id)), t.kind === "error" ? 7000 : 4500);
  }, []);

  return (
    <Ctx.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed bottom-20 right-4 z-[60] flex w-[min(380px,calc(100vw-2rem))] flex-col gap-2" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} role={t.kind === "error" ? "alert" : "status"} className="toast card pointer-events-auto flex gap-3 !rounded-2xl p-3.5">
            <span aria-hidden className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-bold text-white"
              style={{ background: ICON[t.kind].color }}>{ICON[t.kind].icon}</span>
            <div className="min-w-0 text-sm">
              <div className="font-semibold text-ink">{t.title}</div>
              {t.text && <div className="mt-0.5 break-words text-ink-2">{t.text}</div>}
            </div>
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}
