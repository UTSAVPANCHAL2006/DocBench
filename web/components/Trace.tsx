import type { Specimen } from "@/lib/data";

/** One document's path through the AI + checks method, using the run's real intermediate outputs. */
export default function Trace({ s, model }: { s: Specimen; model: string | null }) {
  const { ocr, checks } = s.trace;
  const failed = checks.filter(c => !c.ok);
  const real = failed.filter(c => c.real).length;
  return (
    <ol className="trace">
      <li>
        <div className="step-head"><span className="step-n">1</span><b>Scanned text (OCR)</b><span className="step-sub">what free text-scanning software pulls off the page</span></div>
        <pre className="raw">{ocr || "(nothing recognised)"}</pre>
      </li>
      <li>
        <div className="step-head"><span className="step-n">2</span><b>What the AI read</b><span className="step-sub">{model ?? "AI model"} reading the page image, returned as named fields</span></div>
        <pre className="raw">{s.trace.model}</pre>
      </li>
      <li>
        <div className="step-head"><span className="step-n">3</span><b>Pharmacy and billing checks</b><span className="step-sub">{checks.length - failed.length} of {checks.length} passed</span></div>
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
            : `${failed.length} ${failed.length === 1 ? "check failed" : "checks failed"}, so this document goes to a pharmacist for review. ${real} of ${failed.length} ${failed.length === 1 ? "points" : "point"} at a value the AI really misread.`}
        </p>
      </li>
    </ol>
  );
}
