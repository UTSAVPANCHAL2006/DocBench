"""Export the web app's data from the latest benchmark run.

  .venv/bin/python scripts/export_web_data.py

Reads results/ and the cached model responses, and writes web/data/showcase.json plus the
page images the site shows to web/public/img/. Nothing on the site is typed in by hand, so
re-running the benchmark and then this script keeps every number on it truthful. It never
calls an API: any response missing from the cache is an error.
"""
import collections
import json
import re
import statistics
import sys
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from docbench.config import DEGRADATIONS  # noqa: E402
from docbench.__main__ import GuardedLLM  # noqa: E402
from docbench.evaluate import GROUPS, align_items, score_document  # noqa: E402
from docbench.generate import load_dataset  # noqa: E402
from docbench.ocr import run_ocr  # noqa: E402
from docbench.pipelines import checks, vision_llm  # noqa: E402

WEB = ROOT / "web"
IMG = WEB / "public" / "img"
PIPES = ["ocr_regex", "ocr_reference", "ocr_text_llm", "vision_llm", "vision_verified"]
SHOWN = ["ocr_reference", "ocr_text_llm", "vision_verified"]  # columns in the specimen table
STYLES = ["pad", "emr", "invoice", "claim"]

# Specimens and the one-line note for each. Notes describe what the run actually produced;
# build() fails if a note's claim no longer matches the data (see CHECKS).
SPECIMENS = [
    ("rx_pad_007", "Vision reads “1-2 caps” as “12 caps”. Both are valid sig syntax, so no rule can catch it. "
                   "This is one of the 6 critical errors that still get through."),
    ("rx_pad_013", "Vision misreads QHS (at bedtime) on a clean page. “Q4H5” isn’t a word in any sig, "
                   "so validation flags it for review."),
    ("inv_005", "A faxed invoice. The OCR-text LLM invents two lines that aren’t on the page. Vision reads most of it, "
                "and validation flags line 3 (doesn’t add up) and line 4 (unknown DIN). It misses line 1’s unit price: "
                "the line is backordered, and 0 × any price is still $0.00."),
    ("inv_003", "A blurred invoice. OCR recovers almost nothing; vision reads every field correctly."),
    ("claim_008", "A rejected claim. Vision takes the $12.99 fee for the total and swaps who pays: plan $186.00, "
                  "patient $0.00. A rejected claim pays nothing, so validation flags every amount."),
    ("rx_emr_004", "Speckle noise. Cleaned-up OCR reads it perfectly, but the raw OCR text confuses the LLM."),
    ("claim_017", "A faxed claim. Vision reads Qty 60 as 30, and nothing on the page contradicts it, so it goes "
                  "through unflagged. Its misread DIN isn’t in the catalogue, so that one is caught."),
    ("rx_emr_001", "A clean EMR printout. Every pipeline gets it right; this is the easy case most demos stop at."),
]

LABELS = {
    "patient_name": "Patient", "patient_dob": "Date of birth", "health_card": "Health card",
    "date_written": "Date written", "prescriber_name": "Prescriber", "prescriber_license": "CPSO #",
    "drug_name": "Drug", "strength": "Strength", "sig": "Sig", "quantity": "Quantity", "refills": "Refills",
    "supplier": "Supplier", "invoice_number": "Invoice #", "invoice_date": "Invoice date",
    "account_number": "Account #", "po_number": "PO #", "subtotal": "Subtotal", "hst": "HST",
    "total": "Total", "din": "DIN", "qty_ordered": "Ordered", "qty_shipped": "Shipped",
    "unit_cost": "Unit price", "line_total": "Extension", "carrier": "Carrier", "group_number": "Group #",
    "certificate_id": "Cert / ID", "rx_number": "Rx #", "date_of_service": "Date of service",
    "days_supply": "Days supply", "total_submitted": "Total submitted", "amount_paid": "Plan pays",
    "patient_pays": "Patient pays", "status": "Status", "response_codes": "Response codes",
    "trace_number": "Trace #",
}


def label(field):
    if "." in field:
        group, name = field.split(".", 1)
        n = re.sub(r"\D", "", group)
        prefix = "Line" if group.startswith("line") else "Drug"
        return f"{prefix} {n} · {LABELS.get(name, name)}"
    return LABELS.get(field, field)


def pct(ok, n):
    return round(100 * ok / n, 1) if n else None


class CacheOnly:
    """Stands in for the API client: the page is built only from responses already cached by
    the last run, so building it never makes a paid call."""

    def extract(self, *a, **kw):
        raise RuntimeError("not in cache - run `python -m docbench run` first")


def where(doc, fields, c):
    """Human label for a check's location, and the scored field keys it covers."""
    if not c["group"]:
        return "", c["fields"]
    _, _, prefix, item_fields = GROUPS[doc["doc_type"]]
    rows = fields[c["group"]]
    aligned = align_items(doc["fields"][c["group"]], rows, item_fields)
    j = next(i for i, r in enumerate(aligned) if r is rows[c["row"]])
    return f"{'Drug' if prefix == 'med' else 'Line'} {j + 1}", [f"{prefix}{j + 1}.{k}" for k in c["fields"]]


def read_vision(doc, llm):
    """The model's raw answer for a document plus every check run on it, each marked with
    whether the flagged values really were wrong (compared with ground truth)."""
    fields = vision_llm(doc, llm)["fields"]
    raw = json.loads(json.dumps(fields))  # untouched copy for display
    scored = score_document(doc, {"fields": fields})
    out = []
    for c in checks(doc["doc_type"], fields):
        loc, keys = where(doc, fields, c)
        source = fields[c["group"]][c["row"]] if c["group"] else fields
        out.append({"rule": c["rule"], "ok": c["ok"], "detail": c["detail"], "where": loc,
                    "read": {label(k): str(source.get(k.split(".")[-1], "")) for k in keys},
                    "truth": {label(k): scored[k]["gt"] if k in scored else "" for k in keys},
                    "real": any(not scored[k]["correct"] for k in keys if k in scored)})
    return raw, out


def specimen_image(doc_id):
    """Crop the page to its content (ignoring speckle) and save a web-sized JPEG."""
    src = Image.open(ROOT / "data" / "docs" / f"{doc_id}.png").convert("RGB")
    ink = ImageOps.invert(src.convert("L").filter(ImageFilter.MedianFilter(5))).point(lambda p: 255 if p > 90 else 0)
    box = ink.getbbox() or (0, 0, *src.size)
    pad = 40
    box = (max(0, box[0] - pad), max(0, box[1] - pad), min(src.width, box[2] + pad), min(src.height, box[3] + pad))
    img = src.crop(box)
    img.thumbnail((1000, 1300))
    IMG.mkdir(parents=True, exist_ok=True)
    path = IMG / f"{doc_id}.jpg"
    img.save(path, "JPEG", quality=82, optimize=True, progressive=True)
    return f"img/{doc_id}.jpg", img.size


def build():
    rows = [json.loads(l) for l in (ROOT / "results" / "predictions.jsonl").open()]
    summary = json.loads((ROOT / "results" / "summary.json").read_text())
    by_doc = collections.defaultdict(dict)
    for r in rows:
        by_doc[r["doc_id"]][r["pipeline"]] = r

    headline = []
    for p in PIPES:
        rs = [r for r in rows if r["pipeline"] == p]
        fields = [f for r in rs for f in r["scored"].values()]
        crit = [f for f in fields if f["critical"]]
        wrong_crit = [f for f in crit if not f["correct"] and f["pred"]]
        flags = [f for f in fields if f["flagged"]]
        headline.append({
            "pipeline": p,
            "field_acc": pct(sum(f["correct"] for f in fields), len(fields)),
            "critical_acc": pct(sum(f["correct"] for f in crit), len(crit)),
            "critical_wrong": len(wrong_crit),
            "critical_silent": sum(1 for f in wrong_crit if not f["flagged"]),
            "critical_caught": sum(1 for f in wrong_crit if f["flagged"]),
            "flags": len(flags),
            "false_alarms": sum(1 for f in flags if f["correct"]),
            "docs_flagged": len({r["doc_id"] for r in rs if any(f["flagged"] for f in r["scored"].values())}),
            "hallucinated": sum(1 for f in fields if f["category"] == "hallucinated"),
            "p50_ms": round(statistics.median(r["latency_ms"] for r in rs)),
            "cost_per_1k": round(1000 * sum(r["cost_usd"] for r in rs) / len(rs), 2),
            "docs": len(rs),
        })

    def matrix(key, cols):
        out = {}
        for p in PIPES:
            acc = collections.defaultdict(lambda: [0, 0])
            for r in rows:
                if r["pipeline"] == p:
                    for f in r["scored"].values():
                        a = acc[r[key]]
                        a[0] += f["correct"]
                        a[1] += 1
            out[p] = [pct(*acc[c]) for c in cols]
        return out

    docs_by_id = {d["doc_id"]: d for d in load_dataset()}
    llm = GuardedLLM(CacheOnly(), summary["run"]["model"], summary["run"]["effort"], max_cost=0)
    queue = []
    for doc_id, doc in docs_by_id.items():
        _, doc_checks = read_vision(doc, llm)
        for c in doc_checks:
            if not c["ok"]:
                queue.append({"doc": doc_id, "style": doc["style"], "degradation": doc["degradation"], **c})

    pages = {}
    for doc_id in sorted({q["doc"] for q in queue} | {d for d, _ in SPECIMENS}):
        img, size = specimen_image(doc_id)
        pages[doc_id] = {"img": img, "w": size[0], "h": size[1]}

    specimens = []
    for doc_id, note in SPECIMENS:
        docs = by_doc[doc_id]
        base = docs["vision_verified"]
        fields = list(dict.fromkeys(k for p in SHOWN for k in docs[p]["scored"]))
        img, size = pages[doc_id]["img"], (pages[doc_id]["w"], pages[doc_id]["h"])
        table = []
        for k in fields:
            gt = next((docs[p]["scored"][k]["gt"] for p in SHOWN if k in docs[p]["scored"]), "")
            cells = {}
            for p in SHOWN:
                f = docs[p]["scored"].get(k)
                cells[p] = None if f is None else {"v": f["pred"], "ok": f["correct"], "cat": f["category"], "flag": f["flagged"]}
            table.append({"field": k, "label": label(k), "gt": gt,
                          "critical": any(docs[p]["scored"].get(k, {}).get("critical") for p in SHOWN), "cells": cells})
        acc = {p: pct(sum(f["correct"] for f in docs[p]["scored"].values()), len(docs[p]["scored"])) for p in SHOWN}
        model_json, doc_checks = read_vision(docs_by_id[doc_id], llm)
        trace = {"ocr": run_ocr(docs_by_id[doc_id]["image_path"])[0].strip()[:2400],
                 "model": json.dumps(model_json, indent=2, ensure_ascii=False), "checks": doc_checks}
        specimens.append({"id": doc_id, "style": base["style"], "degradation": base["degradation"], "note": note,
                          "img": img, "w": size[0], "h": size[1], "acc": acc, "rows": table, "trace": trace})

    data = {
        "run": summary["run"],
        "docs": len(by_doc),
        "headline": headline,
        "degradations": DEGRADATIONS,
        "by_degradation": matrix("degradation", DEGRADATIONS),
        "styles": STYLES,
        "by_style": matrix("style", STYLES),
        "specimens": specimens,
        "queue": queue,
        "pages": pages,
    }
    check(data)
    (WEB / "data").mkdir(exist_ok=True)
    (WEB / "data" / "showcase.json").write_text(json.dumps(data, ensure_ascii=False, indent=1))
    print(f"web data: {len(specimens)} specimens, {len(pages)} page images, {len(queue)} alerts, run {data['run']['timestamp']}")


def check(data):
    """Fail the build if a specimen note no longer describes what the data shows."""
    spec = {s["id"]: {r["field"]: r for r in s["rows"]} for s in data["specimens"]}
    vv = lambda d, f: spec[d][f]["cells"]["vision_verified"]
    assert vv("rx_pad_007", "med1.sig")["v"].endswith("12 caps PO Q4-6H PRN pain") and not vv("rx_pad_007", "med1.sig")["flag"]
    assert "Q4H5" in vv("rx_pad_013", "med1.sig")["v"] and vv("rx_pad_013", "med1.sig")["flag"]
    assert {k.split(".")[0] for k, c in spec["inv_005"].items() if c["cells"]["ocr_text_llm"] and c["cells"]["ocr_text_llm"]["cat"] == "hallucinated"} == {"line5", "line6"}
    assert vv("inv_005", "line1.unit_cost")["v"] == "21.51" and not vv("inv_005", "line1.unit_cost")["flag"] and vv("inv_005", "line1.qty_shipped")["v"] == "0"
    assert vv("inv_005", "line3.line_total")["flag"] and vv("inv_005", "line4.din")["flag"]
    assert all(c["cells"]["vision_verified"]["ok"] for c in spec["inv_003"].values() if c["cells"]["vision_verified"])
    assert vv("claim_008", "total_submitted")["v"] == "12.99" and vv("claim_008", "amount_paid")["v"] == "186.00" and vv("claim_008", "amount_paid")["flag"] and vv("claim_008", "patient_pays")["flag"]
    assert all(c["cells"]["ocr_reference"]["ok"] for c in spec["rx_emr_004"].values() if c["cells"]["ocr_reference"])
    assert vv("claim_017", "quantity")["v"] == "30" and not vv("claim_017", "quantity")["flag"] and vv("claim_017", "din")["flag"]
    assert all(c["cells"][p]["ok"] for c in spec["rx_emr_001"].values() for p in SHOWN if c["cells"][p])
    # The review queue is the same validation that produced the headline numbers.
    flagged_docs = {q["doc"] for q in data["queue"]}
    assert len(flagged_docs) == next(h for h in data["headline"] if h["pipeline"] == "vision_verified")["docs_flagged"]
    vv_row = next(h for h in data["headline"] if h["pipeline"] == "vision_verified")
    assert vv_row["critical_silent"] == 6, vv_row


if __name__ == "__main__":
    build()
