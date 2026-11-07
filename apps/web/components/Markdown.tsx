import Link from "next/link";
import type { ReactNode } from "react";

/**
 * Μικρό, ασφαλές markdown για απαντήσεις του AI: παράγραφοι, «- » λίστες, **έντονα**, [κείμενο](/εσωτερικό-link).
 * Ποτέ innerHTML· links ΜΟΝΟ προς σελίδες του dashboard (ξεκινούν με «/»).
 */
function inline(text: string, key: string): ReactNode[] {
  const out: ReactNode[] = [];
  const re = /\*\*([^*]+)\*\*|\[([^\]]+)\]\(([^)\s]+)\)/g;
  let last = 0, m: RegExpExecArray | null, i = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    if (m[1] !== undefined) out.push(<strong key={`${key}-b${i}`} className="font-semibold text-ink">{inline(m[1], `${key}-b${i++}`)}</strong>);
    else if (m[3].startsWith("/") && !m[3].startsWith("//"))
      out.push(<Link key={`${key}-l${i++}`} href={m[3]} className="font-medium text-accent underline decoration-[var(--series-1-wash)] underline-offset-2 hover:decoration-current">{m[2]}</Link>);
    else out.push(m[2]);
    last = re.lastIndex;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

export function Markdown({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  let list: string[] = [];
  const flush = (k: number) => {
    if (!list.length) return;
    blocks.push(
      <ul key={`ul${k}`} className="my-1.5 space-y-1 pl-1">
        {list.map((li, j) => (
          <li key={j} className="flex gap-2"><span aria-hidden className="mt-[0.55em] h-1 w-1 shrink-0 rounded-full bg-[var(--ink-muted)]" /><span>{inline(li, `li${k}-${j}`)}</span></li>
        ))}
      </ul>,
    );
    list = [];
  };
  text.split("\n").forEach((raw, k) => {
    const line = raw.trimEnd();
    const bullet = line.match(/^\s*[-•*]\s+(.*)$/);
    if (bullet) { list.push(bullet[1]); return; }
    flush(k);
    if (line.trim()) blocks.push(<p key={`p${k}`} className="my-1.5">{inline(line, `p${k}`)}</p>);
  });
  flush(-1);
  return <div className="text-sm leading-relaxed text-ink-2">{blocks}</div>;
}
