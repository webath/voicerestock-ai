"use client";
import { useEffect, useState } from "react";

type Mode = "system" | "light" | "dark";
const KEY = "vr-theme";
const LABEL: Record<Mode, string> = { system: "Θέμα: αυτόματο", light: "Θέμα: φωτεινό", dark: "Θέμα: σκοτεινό" };

function apply(m: Mode) {
  const el = document.documentElement;
  if (m === "system") el.removeAttribute("data-theme");
  else el.setAttribute("data-theme", m);
}

/** Αυτόματο → φωτεινό → σκοτεινό. Θυμάται την επιλογή (localStorage, αν επιτρέπεται). */
export function ThemeToggle() {
  const [mode, setMode] = useState<Mode>("system");

  useEffect(() => {
    let saved: Mode = "system";
    try { saved = (localStorage.getItem(KEY) as Mode) ?? "system"; } catch {}
    // eslint-disable-next-line react-hooks/set-state-in-effect -- συγχρονισμός με localStorage μία φορά στο mount
    setMode(saved);
  }, []);

  const next = () => {
    const m: Mode = mode === "system" ? "light" : mode === "light" ? "dark" : "system";
    setMode(m);
    apply(m);
    try { localStorage.setItem(KEY, m); } catch {}
  };

  return (
    <button type="button" onClick={next} className="btn btn-ghost btn-sm !h-9 !w-9 !p-0" aria-label={LABEL[mode]} title={LABEL[mode]}>
      <span aria-hidden className="text-base leading-none">{mode === "light" ? "☀" : mode === "dark" ? "☾" : "◐"}</span>
    </button>
  );
}

/** Τρέχει πριν το React για να μην αναβοσβήνει λάθος θέμα. */
export const themeInitScript = `try{var m=localStorage.getItem("${KEY}");if(m==="light"||m==="dark")document.documentElement.setAttribute("data-theme",m)}catch(e){}`;
