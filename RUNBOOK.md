# Runbook: document extraction benchmark

How to keep the extraction benchmark healthy week to week, and what to do when it isn't.
It is written so someone covering for the AI engineer can follow it without background.

## 1. Routine checks

| When | Command | Takes | What "good" looks like |
|---|---|---|---|
| Every Monday | `python -m docbench run` then `python -m docbench check` | ~3 min OCR-only, longer with LLMs | `check` prints `OK` for every pipeline, exit code 0 |
| After any code, model, prompt or dependency change | Same two commands | | Same |
| Before changing the model or effort | Run both settings on the same dataset, then compare `results/history.csv` rows | | New setting is no worse on critical accuracy and silent errors |

After each run, skim [`results/report.md`](results/report.md). Read the **Example errors** table: it lists critical errors that no pipeline flagged, which are the ones that would reach a patient or a ledger.

Don't regenerate the test set (`generate`) as part of routine checks. `check` only compares runs on the same dataset (fingerprinted from the ground truth), so a new dataset starts a new baseline.

## 2. Reading `check`

```
[ocr_reference] OK  critical acc 55.6%, silent errors 61, p50 904 ms, $0.00/1K
[vision_llm] REGRESSION vs 2026-10-26 09:00:
    - silent errors rose 12 -> 19
```

| Exit code | Meaning | Action |
|---|---|---|
| 0 | Every pipeline is within thresholds of its previous run | None |
| 1 | At least one regression | Go to section 3 |
| 2 | Nothing to compare yet (first run on this dataset/model) | Run again next cycle |

A run is flagged as a regression when any of these happen (set in [`docbench/monitor.py`](docbench/monitor.py)):

| Signal | Threshold |
|---|---|
| Critical-field accuracy | drops more than 2 points |
| Silent errors | rise more than 10% (and by at least 2) |
| p50 latency | rises more than 50% |
| Cost per 1K docs | rises more than 20% |
| Failed documents | any |

## 3. When something breaks

**First step every time:** compare the newest two files in `results/archive/` to see which documents and fields changed. For example:

```bash
python - <<'EOF'
import json, glob
a, b = sorted(glob.glob("results/archive/*.jsonl"))[-2:]
load = lambda f: {(r["doc_id"], r["pipeline"]): r for r in map(json.loads, open(f))}
old, new = load(a), load(b)
for key, r in new.items():
    for field, v in r["scored"].items():
        was = old.get(key, {}).get("scored", {}).get(field, {})
        if was.get("correct") and not v["correct"]:
            print(key, field, repr(v["gt"]), "->", repr(v["pred"]))
EOF
```

### Accuracy dropped, or silent errors rose

1. **Find where it dropped.** In `report.md`, check *Accuracy by document style* and *by degradation*.
   - If only one style dropped, a parser or prompt change hit that style.
   - If every style dropped, suspect a dependency change (Tesseract version, Pillow) or a model change.
2. **Check what changed.** Run `git log -p` since the last good run, and `tesseract --version`.
3. **If the LLM pipelines regressed and nothing in the repo changed,** look at `model` in `history.csv`. The model or its behaviour may have changed. Re-run once to rule out noise before escalating.
4. **Fix it with a test first.** Paste the OCR text or the failing field into a test in `tests/test_docbench.py`, make it fail, then fix the code.

### Every field of one document type comes back `missing`

The parser no longer recognises the layout. The usual cause is a new template, such as a new supplier invoice format or a new EMR printout.

1. Look at a few raw OCR texts:
   ```bash
   python -c "from docbench.ocr import run_ocr; print(run_ocr('data/docs/<id>.png')[0])"
   ```
2. Add the new label variants to the matching parser in [`docbench/ocr.py`](docbench/ocr.py), with a test.

### Documents failed outright (`failed_calls` > 0)

Read the `error` field in `results/predictions.jsonl`.

| Error | Cause | Fix |
|---|---|---|
| `TesseractNotFoundError` | Tesseract missing on this machine | `brew install tesseract` / `apt-get install tesseract-ocr` |
| `AuthenticationError` / "Could not resolve authentication method" | No or expired API key | Set `OPENAI_API_KEY` (gpt-* models) or `ANTHROPIC_API_KEY` / `ant auth login` (claude-* models) |
| `ValueError: No price for …` | Model not in `PRICING` | Add its list price to [`docbench/config.py`](docbench/config.py) so cost is measured, not guessed |
| "N docs NOT run - budget limit hit" | `--max-cost` reached | Not an error. Raise `--max-cost` deliberately, or use `--limit` for a smaller sample. Unrun docs are left out of the report, not scored as blanks. |
| `RateLimitError` (429) | Too many parallel calls | The SDK already retries. If it keeps failing, lower `workers` in `docbench/__main__.py` (default 4). |
| `InternalServerError` / overloaded (5xx) | API-side | Re-run later. Don't change code. |
| `RuntimeError: refused: …` | The model declined the request | Check the document. Report it to the AI engineer if the document is a normal one. |
| `JSONDecodeError` | Malformed model output (shouldn't happen with schema-constrained output) | Save the `doc_id`, re-run it alone, escalate if it repeats |

### Latency or cost rose

- **Cost:** check `model` and the `--effort` used. A cost rise on a re-run can also mean the cache was missed: any change to the prompt, schema, model or effort starts a fresh cache (`results/llm_cache/`). Higher effort means more thinking tokens, which are billed as output. Also check whether the page images got larger.
- **Latency:** an LLM-only rise is usually API load. Re-run before acting. An OCR rise usually means a slower machine or a new Tesseract build.

## 4. Changing things safely

| Change | Do this |
|---|---|
| Add a drug | Add it to `DRUGS` in [`docbench/reference.py`](docbench/reference.py) with its Canadian brand names and marketed strengths. Add look-alike pairs to `LOOK_ALIKE`. Run the tests. |
| Add a claim response code | Only add codes confirmed from an official source (CPhA Pharmacy Claim Standard, payer spec, provincial manual), and note the source in the commit message. |
| Change a parser or prompt | Add a test with real-looking OCR text first. Then run `run` + `check` and confirm no other style regressed. |
| Change the model or effort | Run on the same dataset and compare in `history.csv`. `check` treats a new model as a new baseline. |
| Change how a field is scored | Edit `docbench/evaluate.py`, add a test, then run `python -m docbench rescore`. It re-scores saved predictions with no OCR or LLM calls. |
| Change a threshold | Edit `THRESHOLDS` in `docbench/monitor.py` and explain why in the commit message. |

## 5. Data handling rules

- **This repo holds synthetic data only.** Never commit a real prescription, invoice, claim or anything with a real patient's name, health card number or date of birth. Ontario's PHIPA and federal PIPEDA apply to that data.
- Real or de-identified documents for evaluation live outside the repo, in storage the team has approved. Labels are done with the pharmacist.
- Generated images (`data/docs/`) and run archives are git-ignored. Ground truth and reports are small and safe to commit.

## 6. When to escalate to the AI engineer

- `check` fails twice in a row after a re-run, and the cause isn't one of the cases above.
- Any silent error on a critical field in a **real** (non-synthetic) document.
- The model refuses normal documents, or its behaviour changes without a code change.
- Anything involving real patient data leaving approved storage.
