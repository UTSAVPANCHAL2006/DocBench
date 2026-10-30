"use client";

import { useEffect, useRef, useState } from "react";
import { asset, DEG, STYLE, type Page, type QueueItem } from "@/lib/data";

/** The scanned page next to every alert raised on it: what the model read, what the page says. */
export default function PageViewer({ doc, page, alerts, onClose }: {
  doc: string; page: Page; alerts: QueueItem[]; onClose: () => void;
}) {
  const [zoomed, setZoomed] = useState(false);
  const closeRef = useRef<HTMLButtonElement>(null);
  const first = alerts[0];

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();
    return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = overflow; };
  }, [onClose]);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="pv-title" onClick={e => e.stopPropagation()}>
        <div className="modal-head">
          <div>
            <h3 id="pv-title">{STYLE[first.style]}, {DEG[first.degradation]}</h3>
            <span className="mono">{doc} · {alerts.length} {alerts.length === 1 ? "alert" : "alerts"}</span>
          </div>
          <button ref={closeRef} type="button" className="more" onClick={onClose}>Close</button>
        </div>
        <div className="modal-body">
          <div className={`page${zoomed ? " zoomed" : ""}`} onClick={() => setZoomed(z => !z)}>
            <img src={asset(page.img)} width={page.w} height={page.h} alt={`Scanned page ${doc}`} />
            <span className="page-hint">{zoomed ? "Click to fit" : "Click to zoom"}</span>
          </div>
          <div className="alerts">
            {alerts.map((a, i) => (
              <article key={i} className="alert">
                <div className="alert-head">
                  <b>{a.where && <span className="qwhere">{a.where} · </span>}{a.rule}</b>
                  <span className={`outcome ${a.real ? "real" : "false"}`}>{a.real ? "real misread" : "false alarm"}</span>
                </div>
                <p className="qwhy">{a.detail}</p>
                <table className="cmp">
                  <thead><tr><th>Field</th><th>Model read</th><th>On the page</th></tr></thead>
                  <tbody>
                    {Object.entries(a.read).map(([k, v]) => {
                      const truth = a.truth[k] ?? "";
                      const same = v.replace(/\s/g, "").toLowerCase() === truth.replace(/\s/g, "").toLowerCase();
                      return (
                        <tr key={k}>
                          <th scope="row">{k.replace(/^(Line|Drug) \d+ · /, "")}</th>
                          <td className={same ? "" : "diff"}>{v || "—"}</td>
                          <td>{truth || "—"}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </article>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
