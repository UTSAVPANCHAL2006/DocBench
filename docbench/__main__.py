"""CLI.

  python -m docbench generate [--rx 48] [--inv 24] [--claims 24] [--seed 42]
  python -m docbench run [--pipelines ocr_regex,ocr_reference,ocr_text_llm,vision_llm]
                         [--model claude-opus-5-5|gpt-5.4-nano|...] [--effort low] [--limit N] [--max-cost 1.00]
  python -m docbench rescore   # re-score saved predictions after a scoring change (free)
  python -m docbench check     # regression check vs. the previous run (exit 1 on regression)
"""
import argparse
import hashlib
import json
import shutil
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from .config import DEFAULT_MODEL, DEGRADATIONS, RESULTS_DIR
from .evaluate import score_document, score_field
from .generate import generate, load_dataset
from .monitor import check, dataset_id
from .pipelines import LLM_PIPELINES, PIPELINES
from .report import now, write_report


def cmd_generate(args):
    m = generate(args.rx, args.inv, args.claims, args.seed)
    print(f"Generated {len(m)} documents in data/docs (ground truth in data/ground_truth)")


def _run_one(pipe_name, doc, llm):
    try:
        result = PIPELINES[pipe_name](doc, llm)
        error = None
    except Exception as e:  # one bad doc shouldn't kill the run; it's scored as all-missing
        result, error = {"fields": {}, "flags": [], "latency_ms": 0.0, "cost_usd": 0.0}, f"{type(e).__name__}: {e}"
    return {"doc_id": doc["doc_id"], "doc_type": doc["doc_type"], "degradation": doc["degradation"],
            "style": doc["style"], "pipeline": pipe_name, "latency_ms": result["latency_ms"],
            "cost_usd": result["cost_usd"], "error": error, "flags": result["flags"],
            "scored": score_document(doc, result)}


def cmd_rescore(args):
    """Re-score the saved predictions with the current scoring rules and rebuild the report.
    Costs nothing: no OCR or LLM calls are repeated."""
    path = RESULTS_DIR / "predictions.jsonl"
    if not path.exists():
        sys.exit("No results/predictions.jsonl - run `python -m docbench run` first.")
    rows = [json.loads(l) for l in path.open()]
    for r in rows:
        for field, f in r["scored"].items():
            f["correct"], f["category"] = score_field(field, f["gt"], f["pred"])
    with path.open("w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    prev = json.loads((RESULTS_DIR / "summary.json").read_text())["run"] if (RESULTS_DIR / "summary.json").exists() else {}
    info = {**prev, "timestamp": now() + " (rescored)", "dataset": prev.get("dataset", dataset_id())}
    print(write_report(rows, info))


class BudgetExceeded(RuntimeError):
    pass


class GuardedLLM:
    """Wraps an extractor with a disk cache and a spend cap.

    Cache: an identical request (model, effort, prompt, schema, document) is answered from
    results/llm_cache/ at no cost, so re-runs and pipelines sharing a call (vision_llm and
    vision_verified) pay once. The cached cost is still reported, since that is what the
    extraction costs; only `spent` excludes it.
    Cap: refuses new calls once spend would cross max_cost. Calls run WORKERS at a time, so
    it stops early by the largest call seen x WORKERS to stay under."""

    def __init__(self, llm, model: str, effort: str, max_cost: float):
        from . import llm as llm_mod
        self.llm, self.max_cost, self.spent, self.biggest = llm, max_cost, 0.0, 0.0
        self.lock = threading.Lock()
        self.cache_dir = RESULTS_DIR / "llm_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.salt = json.dumps([model, effort, llm_mod.SYSTEM, llm_mod.OCR_PROMPT, llm_mod.SCHEMAS], sort_keys=True)

    def _key(self, doc_type, image_path=None, ocr_text=None):
        h = hashlib.sha256((self.salt + doc_type).encode())
        h.update(open(image_path, "rb").read() if image_path else (ocr_text or "").encode())
        h.update(b"image" if image_path else b"text")
        return h.hexdigest()

    def extract(self, doc_type, image_path=None, ocr_text=None):
        path = self.cache_dir / f"{self._key(doc_type, image_path, ocr_text)}.json"
        if path.exists():
            return tuple(json.loads(path.read_text()))
        with self.lock:
            if self.spent + self.biggest * WORKERS > self.max_cost:
                raise BudgetExceeded(f"budget ${self.max_cost:.2f} reached (spent ${self.spent:.4f})")
        out = self.llm.extract(doc_type, image_path=image_path, ocr_text=ocr_text)
        with self.lock:
            self.spent += out[2]
            self.biggest = max(self.biggest, out[2])
        path.write_text(json.dumps(out))
        return out


WORKERS = 4


def stratified(docs: list, n: int) -> list:
    """First n docs taken round-robin across (style, degradation) cells, so a small sample
    still covers every document type and every degradation."""
    cells = {}
    for d in docs:
        cells.setdefault((d["style"], d["degradation"]), []).append(d)
    # Order cells degradation-major so the first few picks already span all four document styles.
    order = sorted(cells, key=lambda k: (DEGRADATIONS.index(k[1]), k[0]))
    out, queues = [], [cells[k] for k in order]
    while len(out) < n and any(queues):
        for q in queues:
            if q and len(out) < n:
                out.append(q.pop(0))
    return out


def cmd_run(args):
    docs = load_dataset()
    if not docs:
        sys.exit("No documents found. Run `python -m docbench generate` first.")
    if args.limit:
        docs = stratified(docs, args.limit)
    pipes = args.pipelines.split(",")
    llm = None
    if LLM_PIPELINES & set(pipes):
        try:
            from .llm import make_extractor
            llm = GuardedLLM(make_extractor(args.model, args.effort), args.model, args.effort, args.max_cost)
        except Exception as e:
            print(f"Skipping LLM pipelines (missing credentials or SDK?): {e}")
            pipes = [p for p in pipes if p not in LLM_PIPELINES]

    rows = []
    for p in pipes:
        workers = WORKERS if p in LLM_PIPELINES else 1
        with ThreadPoolExecutor(workers) as pool:
            batch = list(pool.map(lambda d: _run_one(p, d, llm), docs))
        skipped = [r for r in batch if (r["error"] or "").startswith("BudgetExceeded")]
        if skipped:
            # Unrun docs are left out rather than scored as blanks, and reported, so they can't skew accuracy.
            print(f"{p}: {len(skipped)} docs NOT run - budget limit hit. Comparisons across pipelines are only fair on the same docs.")
            batch = [r for r in batch if r not in skipped]
        errors = [r for r in batch if r["error"]]
        print(f"{p}: {len(batch)} docs, {len(errors)} errors" + (f" (first: {errors[0]['error']})" if errors else ""))
        if p in LLM_PIPELINES and len(errors) == len(batch):
            print(f"  every call failed - dropping {p} from the report")
            continue
        rows += batch

    RESULTS_DIR.mkdir(exist_ok=True)
    with (RESULTS_DIR / "predictions.jsonl").open("w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    used_llm = any(p in LLM_PIPELINES for p in {r["pipeline"] for r in rows})
    info = {"timestamp": now(), "dataset": dataset_id() + (f"-first{args.limit}" if args.limit else ""),
            "model": args.model if used_llm else None, "effort": args.effort if used_llm else None}
    if llm:
        print(f"LLM spend this run: ${llm.spent:.4f} (cached calls are free)")
    print(write_report(rows, info))
    # Keep every run's predictions so a regression can be diffed against the run before it.
    archive = RESULTS_DIR / "archive"
    archive.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    shutil.copy(RESULTS_DIR / "predictions.jsonl", archive / f"predictions_{stamp}.jsonl")
    print("Saved results/report.md, results/predictions.jsonl, results/history.csv, results/archive/")


def main():
    ap = argparse.ArgumentParser(prog="docbench")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate")
    g.add_argument("--rx", type=int, default=48)
    g.add_argument("--inv", type=int, default=24)
    g.add_argument("--claims", type=int, default=24)
    g.add_argument("--seed", type=int, default=42)
    r = sub.add_parser("run")
    r.add_argument("--pipelines", default=",".join(PIPELINES))
    r.add_argument("--model", default=DEFAULT_MODEL)
    r.add_argument("--effort", default="low", choices=["low", "medium", "high", "xhigh", "max"])
    r.add_argument("--limit", type=int, default=0, help="run on N docs sampled across every style and degradation")
    r.add_argument("--max-cost", type=float, default=1.00, help="stop LLM calls before spend (USD) crosses this")
    sub.add_parser("check", help="compare the latest run with the previous one; exit 1 on regression")
    sub.add_parser("rescore", help="re-score saved predictions with the current rules (no OCR/LLM calls)")
    args = ap.parse_args()
    if args.cmd == "check":
        sys.exit(check())
    {"generate": cmd_generate, "run": cmd_run, "rescore": cmd_rescore}[args.cmd](args)


if __name__ == "__main__":
    main()
