import type { Specimen } from "@/lib/data";

/** One document's path through the vision + validation pipeline, using the run's real intermediate outputs. */
export default function Trace({ s, model }: { s: Specimen; model: string | null }) {
  const { ocr, checks } = s.trace;
  const failed = checks.filter(c => !c.ok);
  const real = failed.filter(c => c.real).length;
  return (
    <ol className="trace">
      <li>
        <div className="step-head"><span className="step-n">1</span><b>OCR text</b><span className="step-sub">Tesseract, what the text-only pipelines receive</span></div>
        <pre className="raw">{ocr || "(nothing recognised)"}</pre>
      </li>
      <li>
        <div className="step-head"><span className="step-n">2</span><b>Model output</b><span className="step-sub">{model ?? "LLM"} reading the page image, schema-constrained JSON</span></div>
        <pre className="raw">{s.trace.model}</pre>
      </li>
      <li>
        <div className="step-head"><span className="step-n">3</span><b>Validation</b><span className="step-sub">{checks.length - failed.length} of {checks.length} checks passed</span></div>
        <ul className="checks">
          {checks.map((c, i) => (
            <li key={i} className={c.ok ? "pass" : "fail"}>
              <span className="mark">{c.ok ? "pass" : "flag"}</span>
              <span className="rule">{c.where && <em>{c.where} · </em>}{c.rule}</span>
              <span className="detail">{c.detail}</span>
            </li>
          ))}
        </ul>
      </li>
      <li>
        <div className="step-head"><span className="step-n">4</span><b>Result</b></div>
        <p className="result">
          {failed.length === 0
            ? "Every check passed, so the record goes straight through."
            : `${failed.length} ${failed.length === 1 ? "check failed" : "checks failed"}, so this document goes to a pharmacist. ${real} of ${failed.length} ${failed.length === 1 ? "points" : "point"} at a value the model really misread.`}
        </p>
      </li>
    </ol>
  );
}
