"""Regression check: compare the latest run of each pipeline with the previous run on the
same dataset and fail loudly if quality, safety, speed or cost got worse.

  python -m docbench check        exit 0 = healthy, exit 1 = regression, exit 2 = nothing to compare

Meant to run after every `run` (in CI or a weekly cron). See RUNBOOK.md for what to do
when it fails.
"""
import csv
import hashlib

from .config import DATA_DIR, RESULTS_DIR

# A run is a regression if any of these move the wrong way by more than the threshold.
THRESHOLDS = {
    "critical_acc_drop": 0.02,      # absolute, e.g. 0.95 -> 0.929
    "silent_wrong_rise": 0.10,      # relative, and at least 2 more errors
    "p50_ms_rise": 0.50,            # relative
    "cost_per_1k_rise": 0.20,       # relative
}


def dataset_id() -> str:
    """Short fingerprint of the ground truth, so runs on different test sets are never compared."""
    h = hashlib.sha256()
    for p in sorted((DATA_DIR / "ground_truth").glob("*.json")):
        h.update(p.read_bytes())
    return h.hexdigest()[:10]


def compare(prev: dict, cur: dict) -> list:
    problems = []
    pa, ca = float(prev["critical_acc"]), float(cur["critical_acc"])
    if pa - ca > THRESHOLDS["critical_acc_drop"]:
        problems.append(f"critical-field accuracy fell {pa:.1%} -> {ca:.1%}")
    ps, cs = int(prev["silent_wrong"]), int(cur["silent_wrong"])
    if cs - ps >= 2 and cs > ps * (1 + THRESHOLDS["silent_wrong_rise"]):
        problems.append(f"silent errors rose {ps} -> {cs}")
    pl, cl = float(prev["p50_ms"]), float(cur["p50_ms"])
    if pl and cl > pl * (1 + THRESHOLDS["p50_ms_rise"]):
        problems.append(f"p50 latency rose {pl:.0f} -> {cl:.0f} ms")
    pc, cc = float(prev["cost_per_1k"]), float(cur["cost_per_1k"])
    if pc and cc > pc * (1 + THRESHOLDS["cost_per_1k_rise"]):
        problems.append(f"cost per 1K docs rose ${pc:.2f} -> ${cc:.2f}")
    if int(cur.get("failed_calls") or 0):
        problems.append(f"{cur['failed_calls']} documents failed outright (see predictions.jsonl 'error')")
    return problems


def check() -> int:
    hist = RESULTS_DIR / "history.csv"
    if not hist.exists():
        print("No results/history.csv yet - run `python -m docbench run` first.")
        return 2
    rows = list(csv.DictReader(hist.open()))
    status, compared = 0, 0
    for pipe in dict.fromkeys(r["pipeline"] for r in rows):
        runs = [r for r in rows if r["pipeline"] == pipe]
        cur = runs[-1]
        prev = next((r for r in reversed(runs[:-1]) if r["dataset"] == cur["dataset"] and r["model"] == cur["model"]), None)
        if prev is None:
            print(f"[{pipe}] first run on this dataset/model - baseline recorded")
            continue
        compared += 1
        problems = compare(prev, cur)
        if problems:
            status = 1
            print(f"[{pipe}] REGRESSION vs {prev['timestamp']}:")
            for p in problems:
                print(f"    - {p}")
        else:
            print(f"[{pipe}] OK  critical acc {float(cur['critical_acc']):.1%}, silent errors {cur['silent_wrong']}, "
                  f"p50 {cur['p50_ms']} ms, ${cur['cost_per_1k']}/1K")
    return status if compared else (status or 2)
