"""Turn scored predictions into a markdown report + a history row for week-over-week tracking."""
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime

from .config import DEGRADATIONS, RESULTS_DIR

CATEGORIES = ["numeric_mismatch", "missing", "near_miss", "date_mismatch", "wrong_value", "hallucinated"]


def _pct(a, b):
    return f"{100 * a / b:.1f}%" if b else "–"


def _percentile(values, q):
    if not values:
        return 0.0
    values = sorted(values)
    return values[min(len(values) - 1, int(round(q * (len(values) - 1))))]


def _silent(f) -> bool:
    """A wrong value that looks filled-in and carries no review flag. Empty fields are
    excluded: a reviewer can see a blank, but not a plausible-looking wrong number."""
    return not f["correct"] and bool(f["pred"]) and not f["flagged"]


def summarize(rows: list) -> dict:
    """rows: one per (doc, pipeline) with keys doc_id, doc_type, degradation, handwritten,
    pipeline, latency_ms, cost_usd, error, scored."""
    out = {}
    for pipe in dict.fromkeys(r["pipeline"] for r in rows):
        rs = [r for r in rows if r["pipeline"] == pipe]
        fields = [f for r in rs for f in r["scored"].values()]
        wrong = [f for f in fields if not f["correct"]]
        crit = [f for f in fields if f["critical"]]
        out[pipe] = {
            "docs": len(rs),
            "failed_calls": sum(1 for r in rs if r.get("error")),
            "field_acc": sum(f["correct"] for f in fields) / max(1, len(fields)),
            "critical_acc": sum(f["correct"] for f in crit) / max(1, len(crit)),
            "doc_exact": sum(all(f["correct"] for f in r["scored"].values()) for r in rs) / max(1, len(rs)),
            "wrong": len(wrong),
            "silent_wrong": sum(1 for f in wrong if _silent(f)),
            "p50_ms": _percentile([r["latency_ms"] for r in rs], 0.5),
            "p90_ms": _percentile([r["latency_ms"] for r in rs], 0.9),
            "cost_per_1k": 1000 * sum(r["cost_usd"] for r in rs) / max(1, len(rs)),
            "categories": dict(Counter(f["category"] for f in wrong)),
        }
    return out


def _acc_by(rows, pipe, key_fn):
    groups = defaultdict(lambda: [0, 0])
    for r in rows:
        if r["pipeline"] != pipe:
            continue
        for f in r["scored"].values():
            g = groups[key_fn(r)]
            g[0] += f["correct"]
            g[1] += 1
    return groups


def write_report(rows: list, run_info: dict) -> str:
    summary = summarize(rows)
    pipes = list(summary)
    n_docs = len({r["doc_id"] for r in rows})
    L = ["# Extraction benchmark report", "",
         f"Run: {run_info['timestamp']} · {n_docs} synthetic documents · "
         f"LLM: `{run_info.get('model') or 'not run'}` (effort `{run_info.get('effort') or '-'}`)", "",
         "All numbers below were measured in this run. Documents are synthetic (fictional patients, "
         "prescribers and DINs); see the README for what that does and does not tell you.", "",
         "## Headline", "",
         "| Pipeline | Field accuracy | Critical-field accuracy | Docs 100% correct | Wrong fields | Wrong & NOT flagged | p50 latency | p90 latency | Cost / 1K docs |",
         "|---|---|---|---|---|---|---|---|---|"]
    L[-2] = L[-2].replace("Wrong & NOT flagged", "Silent errors")
    for p in pipes:
        s = summary[p]
        L.append(f"| `{p}` | {s['field_acc']:.1%} | {s['critical_acc']:.1%} | {s['doc_exact']:.1%} | {s['wrong']} | "
                 f"{s['silent_wrong']} | {s['p50_ms']:.0f} ms | {s['p90_ms']:.0f} ms | ${s['cost_per_1k']:.2f} |")
    failed = {p: s["failed_calls"] for p, s in summary.items() if s["failed_calls"]}
    if failed:
        L += ["", f"Failed calls (scored as all-missing): {failed}"]
    L += ["", "Critical fields: drug name, strength, sig, quantity, DIN, quantity shipped, unit cost, line total, invoice total, "
          "claim status, plan pays, patient pays, response codes. "
          "\"Silent errors\" = a filled-in but wrong value with no review flag - the kind that reaches a patient or a ledger "
          "(blank fields are excluded because a reviewer can see them).",
          "", "## Accuracy by degradation", "", "| Pipeline | " + " | ".join(DEGRADATIONS) + " |",
          "|---|" + "---|" * len(DEGRADATIONS)]
    for p in pipes:
        g = _acc_by(rows, p, lambda r: r["degradation"])
        L.append(f"| `{p}` | " + " | ".join(_pct(*g[d]) for d in DEGRADATIONS) + " |")

    L += ["", "## Accuracy by document style", "",
          "| Pipeline | Handwritten Rx pad | EMR-printed Rx | Wholesaler invoice | Claim response |", "|---|---|---|---|---|"]
    for p in pipes:
        g = _acc_by(rows, p, lambda r: r["style"])
        L.append(f"| `{p}` | {_pct(*g['pad'])} | {_pct(*g['emr'])} | {_pct(*g['invoice'])} | {_pct(*g['claim'])} |")

    L += ["", "## Accuracy per field", ""]
    fields = list(dict.fromkeys(f.split(".")[-1] for r in rows for f in r["scored"]))
    L += ["| Field | " + " | ".join(f"`{p}`" for p in pipes) + " |", "|---|" + "---|" * len(pipes)]
    for fld in fields:
        cells = []
        for p in pipes:
            ok = n = 0
            for r in rows:
                if r["pipeline"] != p:
                    continue
                for k, f in r["scored"].items():
                    if k.split(".")[-1] == fld:
                        ok += f["correct"]
                        n += 1
            cells.append(_pct(ok, n))
        L.append(f"| {fld} | " + " | ".join(cells) + " |")

    L += ["", "## Error categories", "", "| Pipeline | " + " | ".join(CATEGORIES) + " |", "|---|" + "---|" * len(CATEGORIES)]
    for p in pipes:
        c = summary[p]["categories"]
        L.append(f"| `{p}` | " + " | ".join(str(c.get(k, 0)) for k in CATEGORIES) + " |")

    L += ["", "## Example errors (critical fields, not flagged)", "", "| Pipeline | Doc | Degradation | Field | Truth | Extracted |", "|---|---|---|---|---|---|"]
    for p in pipes:
        shown = 0
        for r in rows:
            if r["pipeline"] != p:
                continue
            for k, f in r["scored"].items():
                if f["critical"] and _silent(f) and shown < 5:
                    L.append(f"| `{p}` | {r['doc_id']} | {r['degradation']} | {k} | `{f['gt']}` | `{f['pred'] or '∅'}` |")
                    shown += 1
    report = "\n".join(L) + "\n"

    RESULTS_DIR.mkdir(exist_ok=True)
    (RESULTS_DIR / "report.md").write_text(report)
    (RESULTS_DIR / "summary.json").write_text(json.dumps({"run": run_info, "pipelines": summary}, indent=2))
    hist = RESULTS_DIR / "history.csv"
    new = not hist.exists()
    with hist.open("a", newline="") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["timestamp", "dataset", "pipeline", "model", "docs", "field_acc", "critical_acc", "silent_wrong",
                        "p50_ms", "cost_per_1k", "failed_calls"])
        for p, s in summary.items():
            w.writerow([run_info["timestamp"], run_info.get("dataset", ""), p, run_info.get("model") if p.endswith("llm") else "",
                        s["docs"], f"{s['field_acc']:.4f}", f"{s['critical_acc']:.4f}", s["silent_wrong"],
                        f"{s['p50_ms']:.0f}", f"{s['cost_per_1k']:.2f}", s["failed_calls"]])
    return report


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")
