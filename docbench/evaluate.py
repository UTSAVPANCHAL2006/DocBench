"""Field-level scoring and error categories.

Values are normalized before comparison (case, whitespace, date format, "$",
"500mg" vs "500 mg", "KHAN, Mei" vs "Mei Khan", "Dr. X, MD" vs "X", and "Lipitor" vs
"APO-ATORVASTATIN" vs "Atorvastatin") so a pipeline isn't penalized for formatting or
for naming the same molecule differently - only for getting the actual value wrong.

Repeated groups (medications on a prescription, lines on an invoice) are aligned
by content before scoring, so one missed row costs that row only.

Error categories for a wrong field:
  missing           ground truth has a value, pipeline returned nothing
  hallucinated      pipeline returned a value that isn't on the page (e.g. a health
                    card number on a script that has none, or an extra invoice line)
  numeric_mismatch  a number is wrong (dose, quantity, price, DIN digit) - safety/money critical
  date_mismatch     a date is wrong
  near_miss         text off by a few characters (typical OCR confusion)
  wrong_value       anything else (e.g. a look-alike drug)
"""
import difflib
import re
from datetime import datetime

from .reference import canonical_drug

RX_FIELDS = ["patient_name", "patient_dob", "health_card", "date_written", "prescriber_name", "prescriber_license"]
MED_FIELDS = ["drug_name", "strength", "sig", "quantity", "refills"]
INV_FIELDS = ["supplier", "invoice_number", "invoice_date", "account_number", "po_number", "subtotal", "hst", "total"]
LINE_FIELDS = ["din", "qty_ordered", "qty_shipped", "unit_cost", "line_total"]
CLAIM_FIELDS = ["carrier", "group_number", "patient_name", "certificate_id", "rx_number", "date_of_service",
                "din", "drug_name", "strength", "quantity", "days_supply", "total_submitted", "amount_paid",
                "patient_pays", "status", "response_codes", "trace_number"]
GROUPS = {"prescription": (RX_FIELDS, "medications", "med", MED_FIELDS),
          "invoice": (INV_FIELDS, "line_items", "line", LINE_FIELDS),
          "claim": (CLAIM_FIELDS, None, None, [])}

CRITICAL = {"drug_name", "strength", "sig", "quantity", "din", "qty_shipped", "unit_cost", "line_total", "total",
            "status", "amount_paid", "patient_pays", "response_codes"}
DATE_FIELDS = {"patient_dob", "date_written", "invoice_date", "date_of_service"}
NUMBER_FIELDS = {"quantity", "refills", "subtotal", "hst", "total", "qty_ordered", "qty_shipped", "unit_cost", "line_total",
                 "days_supply", "total_submitted", "amount_paid", "patient_pays"}
ID_FIELDS = {"din", "invoice_number", "health_card", "prescriber_license", "account_number", "po_number",
             "group_number", "certificate_id", "rx_number", "trace_number"}
NAME_FIELDS = {"patient_name", "prescriber_name"}
_DATE_FORMATS = ["%Y-%m-%d", "%b %d, %Y", "%B %d, %Y", "%d/%m/%Y", "%d-%b-%Y", "%b %d %Y"]


def base_name(field: str) -> str:
    return field.split(".")[-1]


def flatten(doc_type: str, fields: dict) -> dict:
    top, group, prefix, item_fields = GROUPS[doc_type]
    flat = {k: str(fields.get(k, "") or "") for k in top}
    for i, item in enumerate((fields.get(group) or []) if group else [], 1):
        for k in item_fields:
            flat[f"{prefix}{i}.{k}"] = str(item.get(k, "") or "")
    return flat


def _norm_text(s: str) -> str:
    s = re.sub(r"\s+", " ", s.strip().lower())
    return s.strip(" .,:;")


def _norm_name(s: str) -> str:
    s = _norm_text(s)
    s = re.sub(r"^dr\.?\s+", "", s)
    s = re.sub(r",?\s*\b(md|ccfp|frcpc)\b", "", s).strip(" ,")
    if "," in s:  # "khan, mei" -> "mei khan"
        last, first = [p.strip() for p in s.split(",", 1)]
        s = f"{first} {last}"
    return s


def _norm_date(s: str) -> str:
    s = s.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return _norm_text(s)


def _norm_number(s: str):
    try:
        return round(float(s.strip().replace("$", "").replace(",", "")), 2)
    except ValueError:
        return None


def normalize(field: str, value: str):
    name = base_name(field)
    if name in DATE_FIELDS:
        return _norm_date(value)
    if name in NUMBER_FIELDS:
        n = _norm_number(value)
        return n if n is not None else _norm_text(value)
    if name in NAME_FIELDS:
        return _norm_name(value)
    if name == "strength":  # "10 mg tablet" -> "10mg": the dosage form isn't part of the strength
        m = re.match(r"\s*([\d.,]+)\s*(mg|mcg|g|ml)\b", value.lower())
        return f"{m.group(1)}{m.group(2)}" if m else re.sub(r"\s+", "", value.lower())
    if name == "prescriber_license":  # "CPSO #49862" -> "49862"
        return re.sub(r"^\s*CPSO\s*", "", value.upper()).replace("#", "").replace(" ", "")
    if name == "drug_name":  # brand, generic and "APO-" style names of the same molecule are the same drug
        return canonical_drug(value).lower()
    if name == "response_codes":
        return ",".join(sorted(c for c in re.split(r"[\s,;]+", value.upper()) if c))
    if name in ID_FIELDS:
        return re.sub(r"[\s\-#]", "", value.upper())
    if name == "sig":  # the "Sig:" label printed before the directions isn't part of them
        value = re.sub(r"^\s*(sig|directions)\s*[:;.]?\s*", "", value, flags=re.I)
        return re.sub(r"\s*([/\-])\s*", r"\1", _norm_text(value))
    return _norm_text(value)


def score_field(field: str, gt: str, pred: str):
    """Returns (correct, category or None)."""
    g, p = normalize(field, gt), normalize(field, pred)
    if g == p:
        return True, None
    if p in ("", None):
        return False, "missing"
    if g in ("", None):
        return False, "hallucinated"
    name = base_name(field)
    if name in DATE_FIELDS:
        return False, "date_mismatch"
    if name in NUMBER_FIELDS or name in ID_FIELDS or name in ("strength", "response_codes"):
        return False, "numeric_mismatch"
    if difflib.SequenceMatcher(None, str(g), str(p)).ratio() >= 0.8:
        return False, "near_miss"
    return False, "wrong_value"


def align_items(gt_items: list, pred_items: list, item_fields: list) -> list:
    """Reorder predicted rows (meds / invoice lines) to line up with ground truth by
    content, so one skipped row doesn't make every following row count as wrong.
    Unmatched ground-truth rows get an empty row; leftover predictions go at the end
    (scored as hallucinated)."""
    def agree(g, p):
        return sum(normalize(k, str(g.get(k, ""))) == normalize(k, str(p.get(k, ""))) for k in item_fields)

    # Greedy over all (gt, pred) pairs, best agreement first, so a row is paired with
    # the row it matches most - not with the first row that shares, say, a quantity.
    pairs = sorted(((agree(g, p), gi, pi) for gi, g in enumerate(gt_items) for pi, p in enumerate(pred_items)),
                   key=lambda t: (-t[0], t[1], t[2]))
    aligned, used_gt, used_pred = [{}] * len(gt_items), set(), set()
    for score, gi, pi in pairs:
        if score > 0 and gi not in used_gt and pi not in used_pred:
            aligned[gi] = pred_items[pi]
            used_gt.add(gi)
            used_pred.add(pi)
    return aligned + [p for i, p in enumerate(pred_items) if i not in used_pred]


def score_document(doc: dict, result: dict) -> dict:
    _, group, prefix, item_fields = GROUPS[doc["doc_type"]]
    gt = flatten(doc["doc_type"], doc["fields"])
    pred_fields = dict(result.get("fields") or {})
    if group:
        pred_fields[group] = align_items(doc["fields"][group], pred_fields.get(group) or [], item_fields)
    pred = flatten(doc["doc_type"], pred_fields)
    # Row-level review flags travel with their row ("_review"), so they survive alignment.
    flags = set(result.get("flags") or [])
    for i, item in enumerate(pred_fields.get(group) or [] if group else [], 1):
        flags |= {f"{prefix}{i}.{k}" for k in item.get("_review", [])}
    scored = {}
    for field in list(gt) + [k for k in pred if k not in gt]:
        if not gt.get(field, "").strip() and not pred.get(field, "").strip():
            continue  # absent and correctly left blank: not scored, so it can't pad accuracy
        correct, category = score_field(field, gt.get(field, ""), pred.get(field, ""))
        scored[field] = {"gt": gt.get(field, ""), "pred": pred.get(field, ""), "correct": correct,
                         "category": category, "flagged": field in flags,
                         "critical": base_name(field) in CRITICAL}
    return scored
