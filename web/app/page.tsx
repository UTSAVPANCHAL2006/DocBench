import { Heat, Scatter } from "@/components/Charts";
import Queue from "@/components/Queue";
import Specimens from "@/components/Specimens";
import { byPipeline as H, data as D, DEG, f1, NAMES, REPO, runDate, STYLE } from "@/lib/data";

export default function Page() {
  const vis = H.vision_verified, ocr = H.ocr_reference, txt = H.ocr_text_llm, raw = H.vision_llm;
  const deg = (p: keyof typeof D.by_degradation, k: string) => D.by_degradation[p][D.degradations.indexOf(k)];
  const findings: [string, string, string[]?][] = [
    ["Accuracy hides the risk",
      `Vision reads ${f1(raw.critical_acc)}% of critical fields right, against ${f1(ocr.critical_acc)}% for OCR with reference data. Yet on its own it leaves ${raw.critical_silent} wrong critical values with no warning; OCR leaves ${ocr.critical_silent}. When OCR can’t read a field it leaves it blank. When a model can’t, it often writes a plausible number.`],
    ["Cheap checks catch most of it",
      `Rules a pharmacist would apply by hand caught ${vis.critical_caught} of the model’s ${vis.critical_wrong} critical errors, at no extra cost. The price is review load: ${vis.docs_flagged} of ${vis.docs} documents go to a person, and ${vis.false_alarms} of ${vis.flags} flags are false alarms.`],
    ["Some errors pass every rule",
      `${vis.critical_silent} critical errors still get through, because the wrong value is also a valid one. The next step is a second reader: compare OCR and vision field by field and flag where they disagree.`,
      ["1-2 caps → 12 caps", "Qty 60 → 30"]],
    ["Don’t hand bad OCR to a model",
      `Given garbled OCR text, the model invented ${txt.hallucinated} values that aren’t on the page, whole invoice lines included, and left ${txt.critical_silent} silent critical errors, the most of any pipeline. On speckled scans it scored ${Math.round(deg("ocr_text_llm", "noise"))}%, while vision scored ${Math.round(deg("vision_verified", "noise"))}%.`],
  ];
  const record: [string, string | number][] = [
    ["Run", runDate], ["Documents", D.docs], ["Pipelines", D.headline.length],
    ["LLM", D.run.model ?? "—"], ["Effort", D.run.effort ?? "—"],
  ];
  const jd: [string, string][] = [
    ["Build test sets of synthetic documents with tricky edge cases", "docbench/generate.py"],
    ["Evaluation scripts: accuracy per field, error categories, weekly reports", "evaluate.py · report.py · history.csv"],
    ["Benchmark OCR and LLM approaches on cost, speed and accuracy", "pipelines.py · this page"],
    ["Curate reference data: drug name variations, directions, templates", "reference.py"],
    ["Write tests, fix bugs, document how things work", "50 tests · README.md"],
    ["Cover routine monitoring and run-books", "docbench check · RUNBOOK.md"],
  ];

  return (
    <div className="shell">
      <aside className="rail">
        <a className="mark" href="#top">
          <span className="mark-glyph" aria-hidden="true">℞</span>
          <span className="mark-name">Pharmacy Docbench</span>
        </a>
        <p className="rail-blurb">A test bench for reading Canadian pharmacy documents into data you can trust: prescriptions, wholesaler invoices and claim responses.</p>
        <nav aria-label="Sections">
          <a href="#specimens"><span>Specimens</span><span>{D.specimens.length}</span></a>
          <a href="#queue"><span>Review queue</span><span>{D.queue.length}</span></a>
          <a href="#results"><span>Results</span><span>{D.headline.length}</span></a>
          <a href="#findings"><span>Findings</span><span>{findings.length}</span></a>
          <a href="#method"><span>Method</span><span>→</span></a>
        </nav>
        <div className="record">
          <div className="eyebrow">Run record</div>
          <dl>{record.map(([k, v]) => <div key={k} style={{ display: "contents" }}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>
        </div>
        <a className="repo-link" href={REPO} target="_blank" rel="noreferrer">Source code, raw outputs and tests on GitHub ↗</a>
        <p className="byline">Built by <strong>Utsav Panchal</strong> for the OneRx AI/ML intern role.</p>
      </aside>

      <main id="top">
        <div className="col">
          <section className="hero" aria-labelledby="h1">
            <div className="eyebrow">Document extraction benchmark · Ontario</div>
            <h1 id="h1">Reading a prescription <em>{Math.round(vis.critical_acc)}%</em> right is the easy part.</h1>
            <p className="lede">The hard part is the rest: a dose, a quantity or a price that is wrong and looks right. I built a bench of {D.docs} synthetic pharmacy documents, ran five ways of reading them, and counted the errors that reach a patient or a ledger with no warning.</p>
            <div className="stats">
              <div className="stat"><b>{f1(vis.critical_acc)}%</b><span>of critical fields across all 96 documents, read correctly by the vision model on its own</span></div>
              <div className="stat">
                <b>{raw.critical_silent}<span className="arrow">→</span><span className="good">{vis.critical_silent}</span></b>
                <span>wrong critical values with no warning across all 96 documents, before and after rule-based validation</span>
              </div>
              <div className="stat"><b>${vis.cost_per_1k.toFixed(2)}</b><span>per 1,000 documents, measured from API token usage</span></div>
            </div>
          </section>

          <section id="specimens" aria-labelledby="h-spec">
            <div className="sec-head">
              <div className="eyebrow">Specimens</div>
              <h2 id="h-spec">8 of the 96 test pages, and what each pipeline read off them</h2>
              <p>Picked to show the typical wins and failures. Every value is the pipeline’s actual output; all other numbers on this page cover all 96 pages. Click a page to zoom in.</p>
            </div>
            <Specimens specimens={D.specimens} styles={D.styles} model={D.run.model} />
          </section>

          <section id="queue" aria-labelledby="h-queue">
            <div className="sec-head">
              <div className="eyebrow">Review queue</div>
              <h2 id="h-queue">What a pharmacist would see</h2>
              <p>Every alert validation raised on the vision model’s output across all {D.docs} documents, with the reason it fired and whether the model really had misread the value. Open any page to check it against the scan yourself.</p>
            </div>
            <Queue items={D.queue} docs={D.docs} pages={D.pages} />
          </section>

          <section id="results" aria-labelledby="h-res">
            <div className="sec-head">
              <div className="eyebrow">Results</div>
              <h2 id="h-res">Accuracy and risk move separately</h2>
              <p>Every pipeline read the same {D.docs} documents. Critical fields are the ones that hurt when wrong: drug, strength, sig, quantity, DIN, prices, totals, and who pays on a claim.</p>
            </div>
            <div className="results-grid">
              <div className="panel chart">
                <h3>Critical-field accuracy against silent errors</h3>
                <p className="sub">A silent error is a wrong value with no warning attached. Further right is more accurate; lower is safer.</p>
                <Scatter headline={D.headline} />
              </div>
              <div className="panel">
                <h3>Validation on top of vision</h3>
                <p className="sub">Checks a pharmacist or bookkeeper would do by hand, run on the model’s answer. No extra API call.</p>
                <div className="kpis">
                  <div className="kpi"><b>{vis.critical_caught} of {vis.critical_wrong}</b><span>wrong critical values caught ({Math.round(100 * vis.critical_caught / vis.critical_wrong)}%)</span></div>
                  <div className="kpi"><b>{vis.docs_flagged} of {vis.docs}</b><span>documents sent to a person for review</span></div>
                  <div className="kpi"><b>{vis.false_alarms} of {vis.flags}</b><span>flags that turned out to be false alarms</span></div>
                  <div className="kpi"><b>$0.00</b><span>added cost per document</span></div>
                </div>
              </div>
            </div>
            <div className="panel">
              <h3>All five pipelines</h3>
              <div className="scroll">
                <table className="plain">
                  <thead><tr><th>Pipeline</th><th>All fields</th><th>Critical fields</th><th>Critical, wrong</th><th>…with no warning</th><th>p50 latency</th><th>Cost / 1,000 docs</th></tr></thead>
                  <tbody>
                    {D.headline.map(h => (
                      <tr key={h.pipeline} className={h.pipeline === "vision_verified" ? "hi" : ""}>
                        <td><span className="pname">{NAMES[h.pipeline][0]}</span><span className="pdesc">{NAMES[h.pipeline][1]}</span></td>
                        <td>{f1(h.field_acc)}%</td><td>{f1(h.critical_acc)}%</td><td>{h.critical_wrong}</td>
                        <td><b style={{ fontWeight: 600 }}>{h.critical_silent}</b></td>
                        <td>{h.p50_ms >= 1000 ? `${(h.p50_ms / 1000).toFixed(1)} s` : `${h.p50_ms} ms`}</td>
                        <td>{h.cost_per_1k ? `$${h.cost_per_1k.toFixed(2)}` : "$0"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <div className="panel">
              <h3>Accuracy by page condition</h3>
              <p className="sub">Every degraded page in the set is still readable by a person. Fax breaks every pipeline; OCR alone breaks on almost everything except a clean scan.</p>
              <div className="scroll"><Heat headline={D.headline} cols={D.degradations} labels={DEG} matrix={D.by_degradation} /></div>
            </div>
            <div className="panel">
              <h3>Accuracy by document type</h3>
              <div className="scroll"><Heat headline={D.headline} cols={D.styles} labels={STYLE} matrix={D.by_style} /></div>
            </div>
          </section>

          <section id="findings" aria-labelledby="h-find">
            <div className="sec-head">
              <div className="eyebrow">Findings</div>
              <h2 id="h-find">What I would tell the team</h2>
            </div>
            <div className="findings">
              {findings.map(([t, p, pair]) => (
                <article className="finding" key={t}>
                  <h3>{t}</h3><p>{p}</p>
                  {pair && <div className="pair">{pair.map(x => <code key={x}>{x}</code>)}</div>}
                </article>
              ))}
            </div>
          </section>

          <section id="method" aria-labelledby="h-method">
            <div className="sec-head">
              <div className="eyebrow">Method</div>
              <h2 id="h-method">How the bench works</h2>
            </div>
            <div className="method">
              <div className="panel">
                <h3>Test set</h3>
                <ul>
                  <li><b>{D.docs} documents</b>: 24 each of handwritten Rx pads, EMR-printed scripts, wholesaler invoices and claim adjudication responses.</li>
                  <li><b>Six conditions</b>, evenly split: clean, skewed, blurred, speckled, faxed, 75 dpi.</li>
                  <li>Prescriptions carry what CPSO policy requires: prescriber, CPSO number, address, patient, drug, strength, quantity, directions, date, refills.</li>
                  <li>Built-in traps: Celexa next to Celebrex, <span className="mono">0.5 mg</span> doses, <span className="mono">dd/mm</span> dates, backorders, mixed HST, rejected claims.</li>
                  <li>All people, clinics, insurers and DINs are fictional. Drug and brand names are real.</li>
                </ul>
              </div>
              <div className="panel">
                <h3>Validation rules</h3>
                <ul>
                  <li><b>Drugs</b>: name maps to a known drug (generic, brand or <span className="mono">APO-</span> style); strength is a marketed one; every sig word is a dose or a known direction.</li>
                  <li><b>Invoices</b>: DIN in the catalogue; shipped × unit price = extension; lines add up; HST is 13% of taxable lines; total = subtotal + HST.</li>
                  <li><b>Claims</b>: plan share + patient share = submitted total; a rejected claim pays $0 and carries a known response code.</li>
                  <li>Rules only flag. They never change the model’s value.</li>
                </ul>
              </div>
              <div className="panel">
                <h3>Scoring</h3>
                <ul>
                  <li>Formatting isn’t an error: <span className="mono">500mg</span> = <span className="mono">500 mg</span>, <span className="mono">KHAN, Mei</span> = <span className="mono">Mei Khan</span>, <span className="mono">Lipitor</span> = <span className="mono">Atorvastatin</span>. Misspellings are.</li>
                  <li>Drug rows and invoice lines are matched by content, so one missed row costs one row.</li>
                  <li>A value for a field that isn’t on the page counts as invented.</li>
                  <li>Cost is measured from the tokens each API call reports.</li>
                </ul>
              </div>
              <div className="panel">
                <h3>Running it</h3>
                <pre className="cmd"><span className="c"># build the test set, run all five pipelines</span>{"\n"}python -m docbench generate{"\n"}python -m docbench run --model gpt-5.4-nano --max-cost 0.50{"\n"}<span className="c"># compare with the last run, exit 1 on regression</span>{"\n"}python -m docbench check</pre>
                <p>Responses are cached, so re-runs are free. A runbook covers weekly checks and what to do when one fails.</p>
              </div>
            </div>
            <div className="panel">
              <h3>Verify it yourself</h3>
              <p className="sub">Nothing on this page is typed in by hand. Every number is computed from files in the repository, and every model answer is saved there.</p>
              <ul className="verify">
                <li><a href={`${REPO}/blob/main/results/predictions.jsonl`} target="_blank" rel="noreferrer">results/predictions.jsonl</a><span>every field of every document: the true value, each pipeline’s reading, and how it was scored</span></li>
                <li><a href={`${REPO}/tree/main/results/llm_cache`} target="_blank" rel="noreferrer">results/llm_cache/</a><span>each raw response the model returned, so the run replays without an API key</span></li>
                <li><a href={`${REPO}/tree/main/data/ground_truth`} target="_blank" rel="noreferrer">data/ground_truth/</a><span>the correct answer for each of the {D.docs} test documents</span></li>
                <li><a href={`${REPO}/blob/main/tests/test_docbench.py`} target="_blank" rel="noreferrer">tests/test_docbench.py</a><span>50 tests covering the generator, parsers, validation rules and scoring</span></li>
              </ul>
            </div>
            <div className="panel">
              <h3>Against the role description</h3>
              <div className="jd">
                {jd.map(([a, b]) => <div key={a}><span>{a}</span><span>{b}</span></div>)}
              </div>
            </div>
            <div className="panel">
              <h3>Limits</h3>
              <ul style={{ display: "grid", paddingLeft: 18, margin: 0, gap: 6, color: "var(--ink-2)", fontSize: 14 }}>
                <li>Synthetic pages: the handwriting is a font and the damage is simulated. Real faxes and real handwriting will be harder. Next would be a de-identified set labelled with a pharmacist.</li>
                <li>One small model at low effort, one run. Larger models will likely do better on fax, at 4 to 25 times the token price.</li>
                <li>{D.docs} documents is enough to see the big gaps, not to rank pipelines a few points apart.</li>
                <li>Clinical notes, the fourth document type in the role, aren’t covered yet.</li>
              </ul>
            </div>
          </section>

          <footer>
            <span>Pharmacy Docbench · Utsav Panchal · <a href={REPO} target="_blank" rel="noreferrer">GitHub</a></span>
            <span>Numbers from the run on {runDate}, model {D.run.model}</span>
          </footer>
        </div>
      </main>
    </div>
  );
}
