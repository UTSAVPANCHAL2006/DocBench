"use client";

import { useState } from "react";
import { asset, DEG, STYLE, type Cell, type Specimen, type Style } from "@/lib/data";
import Trace from "./Trace";

function ReadCell({ c, gt }: { c: Cell | null; gt: string }) {
  if (!c) return <td className="absent">·</td>;
  const tags = (
    <>
      {c.cat === "hallucinated" && <span className="tag inv">not on page</span>}
      {c.flag && <span className="tag flag">review</span>}
    </>
  );
  if (!c.v) return <td className="blank"><span className="val">{gt ? "blank" : "·"}</span>{tags}</td>;
  return <td className={c.ok ? "ok" : "bad"}><span className="val">{c.v}</span>{tags}</td>;
}

function MiniBar({ name, value, accent }: { name: string; value: number; accent?: boolean }) {
  return (
    <div className={`minibar${accent ? " v" : ""}`}>
      <span>{name}</span>
      <i style={{ ["--w" as string]: `${value}%` }} />
      <em>{Math.round(value)}%</em>
    </div>
  );
}

export default function Specimens({ specimens, styles, model }: { specimens: Specimen[]; styles: Style[]; model: string | null }) {
  const [filter, setFilter] = useState<Style | "all">("all");
  const [currentId, setCurrentId] = useState(specimens[0].id);
  const [zoomed, setZoomed] = useState(false);
  const [tab, setTab] = useState<"readings" | "trace">("readings");

  const visible = specimens.filter(s => filter === "all" || s.style === filter);
  const current = specimens.find(s => s.id === currentId) ?? specimens[0];

  const pick = (id: string, scroll: boolean) => {
    setCurrentId(id);
    setZoomed(false);
    if (scroll) {
      const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      document.getElementById("viewer")?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "nearest" });
    }
  };
  const applyFilter = (f: Style | "all") => {
    setFilter(f);
    const stillVisible = f === "all" || current.style === f;
    if (!stillVisible) {
      const first = specimens.find(s => s.style === f);
      if (first) pick(first.id, false);
    }
  };

  const chips: [Style | "all", string, number][] = [
    ["all", "All", specimens.length],
    ...styles.map(s => [s, STYLE[s], specimens.filter(x => x.style === s).length] as [Style, string, number]),
  ];

  return (
    <>
      <div className="chips" role="group" aria-label="Filter by document type">
        {chips.map(([key, label, n]) => (
          <button key={key} type="button" className="chip" aria-pressed={filter === key} onClick={() => applyFilter(key)}>
            {label}<span className="count">{n}</span>
          </button>
        ))}
      </div>

      <div className="gallery">
        {visible.map(s => (
          <button key={s.id} type="button" className="card" aria-current={s.id === current.id}
            aria-label={`${STYLE[s.style]}, ${DEG[s.degradation]}`} onClick={() => pick(s.id, true)}>
            <div className="thumb"><img src={asset(s.img)} alt="" loading="lazy" /></div>
            <div className="card-body">
              <div className="card-top">
                <span className="card-title">{STYLE[s.style]}</span>
                <span className="deg">{DEG[s.degradation]}</span>
              </div>
              <div className="minibars">
                <MiniBar name="OCR" value={s.acc.ocr_reference} />
                <MiniBar name="Vision" value={s.acc.vision_verified} accent />
              </div>
            </div>
          </button>
        ))}
      </div>

      <div className="viewer" id="viewer" aria-live="polite">
        <div className={`page${zoomed ? " zoomed" : ""}`} onClick={() => setZoomed(z => !z)}>
          <img src={asset(current.img)} width={current.w} height={current.h}
            alt={`${STYLE[current.style]} page, ${DEG[current.degradation]}`} />
          <span className="page-hint">{zoomed ? "Click to fit" : "Click to zoom"}</span>
        </div>
        <div className="readout">
          <div className="readout-head">
            <h3>{STYLE[current.style]}, {DEG[current.degradation]}</h3>
            <span className="mono">{current.id}</span>
          </div>
          <p className="note">{current.note}</p>
          <div className="tabs" role="tablist" aria-label="View">
            <button type="button" role="tab" aria-selected={tab === "readings"} onClick={() => setTab("readings")}>What each pipeline read</button>
            <button type="button" role="tab" aria-selected={tab === "trace"} onClick={() => setTab("trace")}>Trace: vision + validation</button>
          </div>
          {tab === "trace" ? <Trace s={current} model={model} /> : <>
          <div className="legend">
            <span><i className="sw" />Correct</span>
            <span><i className="sw bad" />Wrong</span>
            <span><i className="sw flag" />Flagged for review</span>
            <span><i className="sw blank" />Left blank</span>
            <span><b style={{ fontWeight: 600, color: "var(--ink)" }}>Bold</b>&nbsp;field = critical</span>
          </div>
          <div className="table-wrap">
            <table className="read">
              <thead>
                <tr>
                  <th scope="col">Field</th>
                  <th scope="col">On the page</th>
                  <th scope="col">OCR + reference<small>free</small></th>
                  <th scope="col">OCR text → LLM<small>no image</small></th>
                  <th scope="col">Vision + validation<small>recommended</small></th>
                </tr>
              </thead>
              <tbody>
                {current.rows.map(r => (
                  <tr key={r.field}>
                    <th scope="row" className={r.critical ? "crit" : ""}>{r.label}</th>
                    <td className="truth">{r.gt || <span style={{ color: "var(--ink-3)" }}>not on page</span>}</td>
                    <ReadCell c={r.cells.ocr_reference} gt={r.gt} />
                    <ReadCell c={r.cells.ocr_text_llm} gt={r.gt} />
                    <ReadCell c={r.cells.vision_verified} gt={r.gt} />
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          </>}
        </div>
      </div>
    </>
  );
}
