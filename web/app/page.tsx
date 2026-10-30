import { Heat, Scatter } from "@/components/Charts";
import Queue from "@/components/Queue";
import Specimens from "@/components/Specimens";
import { byPipeline as H, data as D, DEG, f1, NAMES, REPO, runDate, STYLE } from "@/lib/data";

export default function Page() {
  const checked = H.vision_verified, ocr = H.ocr_reference, txt = H.ocr_text_llm, ai = H.vision_llm;
  const deg = (p: keyof typeof D.by_degradation, k: string) => D.by_degradation[p][D.degradations.indexOf(k)];
  const findings: [string, string, string[]?][] = [
    ["A high accuracy score hides the risk",
      `Reading the page image, the AI gets ${f1(ai.critical_acc)}% of critical fields right, against ${f1(ocr.critical_acc)}% for OCR with pharmacy data. But it leaves ${ai.critical_silent} critical values wrong with no warning; OCR leaves ${ocr.critical_silent}. When OCR can’t read a field, it leaves it blank. When the AI can’t, it often writes down a plausible number instead.`],
    ["Simple checks catch most of it",
      `Checks a pharmacist or bookkeeper already does by hand caught ${checked.critical_caught} of the AI’s ${checked.critical_wrong} critical errors, at no extra cost. The trade-off is review work: ${checked.docs_flagged} of ${checked.docs} documents go to a person.`],
    ["Some errors pass every check",
      `${checked.critical_silent} critical errors still get through, because the wrong value is also a believable one. The next step is a second reader: compare the OCR and AI readings field by field and flag any field where they disagree.`,
      ["1-2 caps → 12 caps", "Qty 60 → 30"]],
    ["Don’t give the AI messy scanned text",
      `Given garbled OCR text instead of the page, the AI invented ${txt.hallucinated} values that aren’t on the page, including whole invoice lines, and left ${txt.critical_silent} critical errors unflagged, the most of any method. On speckled scans it got ${Math.round(deg("ocr_text_llm", "noise"))}% of fields right; reading the page itself, ${Math.round(deg("vision_verified", "noise"))}%.`],
  ];
  const record: [string, string | number][] = [
    ["Run", runDate], ["Test documents", D.docs], ["Methods compared", D.headline.length], ["AI model", D.run.model ?? "—"],
  ];
  const repo: [string, string][] = [
    ["Test-document generator: Rx pads, EMR scripts, invoices, claim responses", "docbench/generate.py"],
    ["Drug names, brands, sig terms and DIN reference list", "docbench/reference.py"],
    ["The five reading methods and the pharmacy checks", "docbench/pipelines.py"],
    ["Scoring per field, error types and weekly report", "docbench/evaluate.py · report.py"],
    ["Regression check and a runbook for whoever covers the system", "docbench/monitor.py · RUNBOOK.md"],
    ["50 automated tests", "tests/test_docbench.py"],
  ];
  const ms = (n: number) => (n >= 1000 ? `${(n / 1000).toFixed(1)} s` : `${n} ms`);

  return (
    <div className="shell">
      <aside className="rail">
        <a className="mark" href="#top">
          <span className="mark-glyph" aria-hidden="true">℞</span>
          <span className="mark-name">Pharmacy Docbench</span>
        </a>
        <p className="rail-blurb">A test bench for turning Canadian pharmacy paperwork into data you can trust: prescriptions, wholesaler invoices and claim responses.</p>
        <nav aria-label="Sections">
          <a href="#specimens"><span>Sample documents</span><span>{D.specimens.length}</span></a>
          <a href="#queue"><span>Review queue</span><span>{D.queue.length}</span></a>
          <a href="#results"><span>Results</span><span>{D.headline.length}</span></a>
          <a href="#findings"><span>Findings</span><span>{findings.length}</span></a>
          <a href="#method"><span>How it works</span><span>→</span></a>
        </nav>
        <div className="record">
          <div className="eyebrow">This run</div>
          <dl>{record.map(([k, v]) => <div key={k} style={{ display: "contents" }}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>
        </div>
        <a className="repo-link" href={REPO} target="_blank" rel="noreferrer">Source code, raw results and tests on GitHub ↗</a>
        <p className="byline">Built by <strong>Utsav Panchal</strong></p>
      </aside>

      <main id="top">
        <div className="col">
          <section className="hero" aria-labelledby="h1">
            <div className="eyebrow">Pharmacy document reading · Ontario</div>
            <h1 id="h1">Reading pharmacy paperwork <em>{Math.round(checked.critical_acc)}%</em> right is the easy part.</h1>
            <p className="lede">The hard part is the rest: a dose, a quantity or a price that is wrong but looks right. I built {D.docs} realistic test documents, read them five different ways, and counted every error that would reach a patient record or a ledger without anyone being warned.</p>
            <div className="stats">
              <div className="stat"><b>{f1(checked.critical_acc)}%</b><span>of critical fields read correctly by the AI, across all {D.docs} documents</span></div>
              <div className="stat">
                <b>{ai.critical_silent}<span className="arrow">→</span><span className="good">{checked.critical_silent}</span></b>
                <span>wrong critical values with no warning, before and after adding pharmacy checks</span>
              </div>
              <div className="stat"><b>${checked.cost_per_1k.toFixed(2)}</b><span>AI cost per 1,000 documents, as billed</span></div>
            </div>
          </section>

          <section id="specimens" aria-labelledby="h-spec">
            <div className="sec-head">
              <div className="eyebrow">Sample documents</div>
              <h2 id="h-spec">8 of the 96 test documents, and what each method read</h2>
              <p>Chosen to show typical successes and failures. Every value is exactly what each method returned; all other numbers on this page cover all 96 documents. Click a page to zoom in.</p>
            </div>
            <Specimens specimens={D.specimens} styles={D.styles} model={D.run.model} />
          </section>

          <section id="queue" aria-labelledby="h-queue">
            <div className="sec-head">
              <div className="eyebrow">Review queue</div>
              <h2 id="h-queue">What a pharmacist would see</h2>
              <p>Every alert the checks raised on the AI’s readings, across all {D.docs} documents: why it fired, and whether the AI had really misread the value. Open any page to compare it with the original scan.</p>
            </div>
            <Queue items={D.queue} docs={D.docs} pages={D.pages} />
          </section>

          <section id="results" aria-labelledby="h-res">
            <div className="sec-head">
              <div className="eyebrow">Results</div>
              <h2 id="h-res">Accuracy and risk are different things</h2>
              <p>All five methods read the same {D.docs} documents. Critical fields are the ones that cause harm or cost money when wrong: drug, strength, directions, quantity, DIN, prices, totals, and who pays on a claim.</p>
            </div>
            <div className="results-grid">
              <div className="panel chart">
                <h3>Critical-field accuracy against unflagged errors</h3>
                <p className="sub">An unflagged error is a wrong value with no warning attached. Further right is more accurate; lower is safer.</p>
                <Scatter headline={D.headline} />
              </div>
              <div className="panel">
                <h3>Adding checks to the AI</h3>
                <p className="sub">Checks a pharmacist or bookkeeper already does by hand, run on the AI’s answer. No extra AI cost.</p>
                <div className="kpis">
                  <div className="kpi"><b>{checked.critical_caught} of {checked.critical_wrong}</b><span>wrong critical values caught ({Math.round(100 * checked.critical_caught / checked.critical_wrong)}%)</span></div>
                  <div className="kpi"><b>{checked.docs_flagged} of {checked.docs}</b><span>documents sent to a person for review</span></div>
                  <div className="kpi"><b>{checked.false_alarms} of {checked.flags}</b><span>flagged fields that were actually correct</span></div>
                  <div className="kpi"><b>$0.00</b><span>extra cost per document</span></div>
                </div>
              </div>
            </div>
            <div className="panel">
              <h3>All five methods</h3>
              <div className="scroll">
                <table className="plain">
                  <thead><tr><th>Method</th><th>All fields correct</th><th>Critical fields correct</th><th>Critical errors</th><th>…with no warning</th><th>Typical time per page</th><th>AI cost / 1,000 docs</th></tr></thead>
                  <tbody>
                    {D.headline.map(h => (
                      <tr key={h.pipeline} className={h.pipeline === "vision_verified" ? "hi" : ""}>
                        <td><span className="pname">{NAMES[h.pipeline][0]}</span><span className="pdesc">{NAMES[h.pipeline][1]}</span></td>
                        <td>{f1(h.field_acc)}%</td><td>{f1(h.critical_acc)}%</td><td>{h.critical_wrong}</td>
                        <td><b style={{ fontWeight: 600 }}>{h.critical_silent}</b></td>
                        <td>{ms(h.p50_ms)}</td>
                        <td>{h.cost_per_1k ? `$${h.cost_per_1k.toFixed(2)}` : "free"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <div className="panel">
              <h3>Fields read correctly, by page condition</h3>
              <p className="sub">Every damaged page in the test set is still readable by a person. Faxes are hardest for every method; OCR alone struggles with almost anything but a clean scan.</p>
              <div className="scroll"><Heat headline={D.headline} cols={D.degradations} labels={DEG} matrix={D.by_degradation} /></div>
            </div>
            <div className="panel">
              <h3>Fields read correctly, by document type</h3>
              <div className="scroll"><Heat headline={D.headline} cols={D.styles} labels={STYLE} matrix={D.by_style} /></div>
            </div>
          </section>

          <section id="findings" aria-labelledby="h-find">
            <div className="sec-head">
              <div className="eyebrow">Findings</div>
              <h2 id="h-find">What the results say</h2>
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
              <div className="eyebrow">How it works</div>
              <h2 id="h-method">How the test bench works</h2>
            </div>
            <div className="method">
              <div className="panel">
                <h3>Test documents</h3>
                <ul>
                  <li><b>{D.docs} documents</b>: 24 each of handwritten prescriptions, prescriptions printed from a clinic EMR, wholesaler invoices and insurance claim responses.</li>
                  <li><b>Six page conditions</b>, evenly split: clean scan, crooked scan, blurry photo, speckled scan, fax, low-resolution scan.</li>
                  <li>Prescriptions include what the CPSO prescribing policy requires: prescriber, CPSO number, practice address, patient, drug, strength, quantity, directions, date and refills.</li>
                  <li>Deliberate traps: Celexa and Celebrex on one script, <span className="mono">0.5 mg</span> doses, <span className="mono">dd/mm</span> dates, backorders, mixed HST, rejected claims.</li>
                  <li>All patients, prescribers, clinics, insurers and DINs are made up. Drug and brand names are real.</li>
                </ul>
              </div>
              <div className="panel">
                <h3>The checks</h3>
                <ul>
                  <li><b>Prescriptions</b>: the drug (generic, brand or <span className="mono">APO-</span> style name) and its strength are on the reference list, and the directions use only known sig terms.</li>
                  <li><b>Invoices</b>: the DIN is on the reference list; shipped × unit price = extension; lines add up to the subtotal; HST is 13% of taxable lines; total = subtotal + HST.</li>
                  <li><b>Claim responses</b>: plan pays + patient pays = total submitted; a rejected claim pays nothing and gives a known reason code.</li>
                  <li>Checks only flag a value for review. They never change it.</li>
                </ul>
              </div>
              <div className="panel">
                <h3>Scoring</h3>
                <ul>
                  <li>Formatting doesn’t count as an error: <span className="mono">500mg</span> = <span className="mono">500 mg</span>, <span className="mono">KHAN, Mei</span> = <span className="mono">Mei Khan</span>, <span className="mono">Lipitor</span> = <span className="mono">atorvastatin</span>. Misspellings do count.</li>
                  <li>Drugs on a script and lines on an invoice are matched by content, so one missed line costs only that line.</li>
                  <li>A value for a field that isn’t on the page counts as invented.</li>
                  <li>AI cost is the amount the provider billed for each document.</li>
                </ul>
              </div>
              <div className="panel">
                <h3>Running it</h3>
                <pre className="cmd"><span className="c"># create the 96 test documents, read them five ways</span>{"\n"}python -m docbench generate{"\n"}python -m docbench run --model gpt-5.4-nano --max-cost 0.50{"\n"}<span className="c"># compare with the previous run; fails if results got worse</span>{"\n"}python -m docbench check</pre>
                <p>AI responses are saved, so re-running costs nothing. A runbook covers the weekly check and what to do when it fails.</p>
              </div>
            </div>
            <div className="panel">
              <h3>Check it yourself</h3>
              <p className="sub">Nothing on this page is typed in by hand. Every number is calculated from files in the repository, and every AI answer is saved there.</p>
              <ul className="verify">
                <li><a href={`${REPO}/blob/main/results/predictions.jsonl`} target="_blank" rel="noreferrer">results/predictions.jsonl</a><span>every field of every document: the correct value, what each method read, and how it was scored</span></li>
                <li><a href={`${REPO}/tree/main/results/llm_cache`} target="_blank" rel="noreferrer">results/llm_cache/</a><span>each answer the AI returned, so the run can be repeated without an API key</span></li>
                <li><a href={`${REPO}/tree/main/data/ground_truth`} target="_blank" rel="noreferrer">data/ground_truth/</a><span>the correct values for each of the {D.docs} test documents</span></li>
                <li><a href={`${REPO}/blob/main/tests/test_docbench.py`} target="_blank" rel="noreferrer">tests/test_docbench.py</a><span>50 automated tests for the documents, the readers, the checks and the scoring</span></li>
              </ul>
            </div>
            <div className="panel">
              <h3>What’s in the repository</h3>
              <div className="jd">
                {repo.map(([a, b]) => <div key={a}><span>{a}</span><span>{b}</span></div>)}
              </div>
            </div>
            <div className="panel">
              <h3>Limits</h3>
              <ul style={{ display: "grid", paddingLeft: 18, margin: 0, gap: 6, color: "var(--ink-2)", fontSize: 14 }}>
                <li>The documents are realistic but made up: the handwriting is a font and the damage is simulated. Real faxes and real handwriting will be harder. The next step would be a set of de-identified real documents, checked by a pharmacist.</li>
                <li>One small, low-cost AI model, run once. Larger models will likely do better on faxes, at 4 to 25 times the price.</li>
                <li>{D.docs} documents is enough to see the big differences, not to rank methods a few points apart.</li>
                <li>Clinical notes aren’t covered yet.</li>
              </ul>
            </div>
          </section>

          <footer>
            <span>Pharmacy Docbench · Utsav Panchal · <a href={REPO} target="_blank" rel="noreferrer">GitHub</a></span>
            <span>Results from the run on {runDate}, AI model {D.run.model}</span>
          </footer>
        </div>
      </main>
    </div>
  );
}
