"use client";

import { useState } from "react";
import { DEG, STYLE, type Page, type QueueItem } from "@/lib/data";
import PageViewer from "./PageViewer";

type Show = "all" | "real" | "false";

/** Every alert validation raised on the vision model's output, as a pharmacist's review inbox. */
export default function Queue({ items, docs, pages }: { items: QueueItem[]; docs: number; pages: Record<string, Page> }) {
  const [show, setShow] = useState<Show>("all");
  const [expanded, setExpanded] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const real = items.filter(i => i.real).length;
  const flaggedDocs = new Set(items.map(i => i.doc)).size;
  const list = items.filter(i => show === "all" || (show === "real") === i.real);
  const visible = expanded ? list : list.slice(0, 10);
  const chips: [Show, string, number][] = [["all", "All alerts", items.length], ["real", "Real misreads", real], ["false", "False alarms", items.length - real]];

  return (
    <div className="panel queue">
      <div className="queue-sum">
        <div><b>{items.length}</b><span>alerts</span></div>
        <div><b>{flaggedDocs} of {docs}</b><span>documents need a look</span></div>
        <div><b>{real} of {items.length}</b><span>alerts were real misreads</span></div>
      </div>
      <div className="chips" role="group" aria-label="Filter alerts">
        {chips.map(([k, label, n]) => (
          <button key={k} type="button" className="chip" aria-pressed={show === k} onClick={() => { setShow(k); setExpanded(false); }}>
            {label}<span className="count">{n}</span>
          </button>
        ))}
      </div>
      <div className="scroll">
        <table className="qtable">
          <thead>
            <tr><th>Document</th><th>Check that failed</th><th>What the model read</th><th>Why it was flagged</th><th>Turned out</th><th><span className="sr-only">Page</span></th></tr>
          </thead>
          <tbody>
            {visible.map((q, i) => (
              <tr key={`${q.doc}-${i}`}>
                <td><span className="qdoc">{STYLE[q.style]}, {DEG[q.degradation]}</span><span className="qid">{q.doc}</span></td>
                <td>{q.where && <span className="qwhere">{q.where} · </span>}{q.rule}</td>
                <td className="qread">{Object.entries(q.read).map(([k, v]) => <div key={k}><span>{k.replace(/^(Line|Drug) \d+ · /, "")}</span> {v || "—"}</div>)}</td>
                <td className="qwhy">{q.detail}</td>
                <td><span className={`outcome ${q.real ? "real" : "false"}`}>{q.real ? "real misread" : "false alarm"}</span></td>
                <td><button type="button" className="open-page" onClick={() => setOpen(q.doc)}>Open page</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {open && (
        <PageViewer doc={open} page={pages[open]} alerts={items.filter(i => i.doc === open)} onClose={() => setOpen(null)} />
      )}
      {list.length > 10 && (
        <button type="button" className="more" onClick={() => setExpanded(e => !e)}>
          {expanded ? "Show fewer" : `Show all ${list.length}`}
        </button>
      )}
    </div>
  );
}
