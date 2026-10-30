"""The extraction approaches being compared.

ocr_regex      Tesseract + regex. Free, fast, brittle.
ocr_reference  Tesseract on raw + noise-cleaned page (keeps the better parse), then
               reference-data repair (drug list, DIN catalogue, sig vocabulary,
               invoice arithmetic). Free. Flags what it can't verify.
               Claims: plan + patient share = submitted total, rejection <=> codes and $0 paid.
ocr_text_llm    Tesseract text -> LLM (no image). Cheap LLM tokens.
vision_llm      Page image -> LLM. Most expensive.
vision_verified vision_llm + the same reference checks, flag-only (values untouched).

Every pipeline returns {"fields", "flags", "latency_ms", "cost_usd"}.
"flags" lists field names the pipeline itself marks for human review.
"""
import re
import time

from . import reference as ref
from .ocr import parse_claim, parse_invoice, parse_prescription, parsed_count, run_ocr

PARSERS = {"prescription": parse_prescription, "invoice": parse_invoice, "claim": parse_claim}


def ocr_regex(doc, llm=None):
    text, ocr_ms = run_ocr(doc["image_path"])
    start = time.perf_counter()
    fields = PARSERS[doc["doc_type"]](text)
    return {"fields": fields, "flags": [], "latency_ms": ocr_ms + (time.perf_counter() - start) * 1000,
            "cost_usd": 0.0}


def _money(s):
    try:
        return float(ref.fix_digits(s).replace(",", ""))
    except ValueError:
        return None


def _repair(doc_type: str, f: dict) -> list:
    """Fix what reference data can fix deterministically in OCR output (O->0, a misspelt drug
    snapped to the list, sig typos). Returns field flags; row flags go in each row's "_review"."""
    flags = []
    if doc_type == "prescription":
        f["prescriber_license"] = ref.fix_digits(f["prescriber_license"])
        hcn = re.match(r"(.*?)([A-Z]{2})?$", f["health_card"])  # digits, then a 2-letter version code
        f["health_card"] = ref.fix_digits(hcn.group(1)) + (hcn.group(2) or "")
        for med in f["medications"]:
            med["_review"] = []
            med["drug_name"], review = ref.match_drug(med["drug_name"])
            if review:
                med["_review"].append("drug_name")
            med["strength"] = ref.normalize_strength(med["strength"])
            med["sig"] = ref.correct_sig(med["sig"])
            for k in ("quantity", "refills"):
                med[k] = ref.fix_digits(med[k])
    elif doc_type == "invoice":
        for line in f["line_items"]:
            line["_review"] = []
            if line["din"]:
                line["din"], review = ref.repair_din(line["din"])
                if review:  # a 1-digit-off DIN snapped to the catalogue is a guess: keep it flagged
                    line["_review"].append("din")
            for k in ("qty_ordered", "qty_shipped", "unit_cost", "line_total"):
                line[k] = ref.fix_digits(line[k]).replace(",", "")
    else:
        if f["din"]:
            f["din"], review = ref.repair_din(f["din"])
            if review:
                flags.append("din")
        f["drug_name"], review = ref.match_drug(f["drug_name"])
        if review:
            flags.append("drug_name")
        f["strength"] = ref.normalize_strength(f["strength"])
        for k in ("total_submitted", "amount_paid", "patient_pays", "quantity", "days_supply"):
            f[k] = ref.fix_digits(f[k]).replace(",", "")
    return flags


def _taxable(line) -> bool:
    return str(line.get("taxable", "")).strip().lower() in ("true", "t", "yes", "y", "1")


def _fmt(v):
    return "?" if v is None else f"{v:.2f}"


def checks(doc_type: str, f: dict) -> list:
    """Every check a pharmacist or bookkeeper would do by hand, with its outcome and the reason.
    Each item: {"rule", "ok", "detail", "fields", "group", "row"}; group/row locate a drug or
    invoice line (row is 0-based), or are None for a document-level check."""
    out = []

    def add(rule, ok, detail, fields, group=None, row=None):
        out.append({"rule": rule, "ok": bool(ok), "detail": detail, "fields": fields, "group": group, "row": row})

    if doc_type == "prescription":
        for i, med in enumerate(f.get("medications") or []):
            g = ("medications", i)
            name = str(med.get("drug_name", ""))
            drug = ref.canonical_drug(name)
            known = drug.lower() in ref.DRUG_BY_NAME
            add("Drug is in the reference list", known,
                (f"“{name}” is {drug}" if drug.lower() != name.lower() else f"{drug} is listed") if known
                else f"“{name}” matches no known drug, brand or generic", ["drug_name"], *g)
            strength = ref.normalize_strength(str(med.get("strength", "")))
            add("Strength is a marketed one", ref.strength_is_known(drug, strength),
                f"{drug} {strength}" + ("" if ref.strength_is_known(drug, strength)
                                        else f" isn’t marketed (known: {', '.join(ref.DRUG_BY_NAME[drug.lower()]['strengths'])})" if known
                                        else " can’t be checked"), ["strength"], *g)
            bad = [k for k in ("quantity", "refills") if not str(med.get(k, "")).isdigit()]
            add("Quantity and refills are whole numbers", not bad,
                f"quantity {med.get('quantity', '')!s}, refills {med.get('refills', '')!s}", bad or ["quantity", "refills"], *g)
            sig = str(med.get("sig", ""))
            ok = ref.sig_is_plausible(sig)
            vocab = {v.lower() for v in ref.SIG_VOCAB}
            unknown = [w.strip(",.;:") for w in re.sub(r"^\s*(sig|directions)\s*[:;.]?\s*", "", sig, flags=re.I).split()
                       if not re.fullmatch(r"[\d/\-.]+", w.strip(",.;:")) and w.strip(",.;:").lower() not in vocab]
            add("Every sig word is a dose or a known direction", ok,
                "all words recognised" if ok else ("unknown: " + ", ".join(f"“{w}”" for w in unknown) if unknown else "sig is empty"),
                ["sig"], *g)
    elif doc_type == "invoice":
        rx_sum = taxable_sum = 0.0
        for i, line in enumerate(f.get("line_items") or []):
            g = ("line_items", i)
            if line.get("din"):
                din = ref.fix_digits(str(line["din"]))
                add("DIN is in the catalogue", din in ref.DIN_SET,
                    f"{din} {'found' if din in ref.DIN_SET else 'not found'}", ["din"], *g)
            o, sh, u, t = (_money(str(line.get(k, ""))) for k in ("qty_ordered", "qty_shipped", "unit_cost", "line_total"))
            ok = None not in (o, sh, u, t) and abs(sh * u - t) <= 0.011 and sh <= o
            if None in (o, sh, u, t):
                detail = "a quantity or price is missing"
            elif sh > o:
                detail = f"shipped {sh:g} is more than ordered {o:g}"
            else:
                detail = f"{sh:g} × {_fmt(u)} = {_fmt(sh * u)}" + ("" if ok else f", page says {_fmt(t)}")
            add("Shipped × unit price = extension", ok, detail, ["qty_ordered", "qty_shipped", "unit_cost", "line_total"], *g)
            if _taxable(line):
                taxable_sum += t or 0.0
            else:
                rx_sum += t or 0.0
        sub, hst, total = (_money(str(f.get(k, ""))) for k in ("subtotal", "hst", "total"))
        lines = rx_sum + taxable_sum
        add("Lines add up to the subtotal", sub is not None and abs(sub - lines) <= 0.011 and bool(f.get("line_items")),
            f"lines sum to {_fmt(lines)}, subtotal {_fmt(sub)}", ["subtotal"])
        due = round(taxable_sum * ref.HST_RATE, 2)
        add("HST is 13% of taxable lines", hst is not None and abs(hst - due) <= 0.011,
            f"13% of {_fmt(taxable_sum)} = {_fmt(due)}, HST {_fmt(hst)}", ["hst"])
        add("Total = subtotal + HST", None not in (sub, hst, total) and abs(total - sub - hst) <= 0.011,
            f"{_fmt(sub)} + {_fmt(hst)} = {_fmt(None if None in (sub, hst) else sub + hst)}, total {_fmt(total)}", ["total"])
    else:  # claim response
        din = ref.fix_digits(str(f.get("din", "")))
        add("DIN is in the catalogue", bool(f.get("din")) and din in ref.DIN_SET,
            f"{din or 'no DIN'} {'found' if din in ref.DIN_SET else 'not found'}", ["din"])
        name = str(f.get("drug_name", ""))
        drug = ref.canonical_drug(name)
        strength = ref.normalize_strength(str(f.get("strength", "")))
        ok = drug.lower() in ref.DRUG_BY_NAME and ref.strength_is_known(drug, strength)
        add("Drug and strength are known", ok, f"“{name}” → {drug} {strength}" + ("" if ok else ", not a known product"),
            ["drug_name", "strength"])
        total, paid, patient = (_money(str(f.get(k, ""))) for k in ("total_submitted", "amount_paid", "patient_pays"))
        ok = None not in (total, paid, patient) and abs(paid + patient - total) <= 0.011
        add("Plan share + patient share = total", ok,
            f"{_fmt(paid)} + {_fmt(patient)} = {_fmt(None if None in (paid, patient) else paid + patient)}, total {_fmt(total)}",
            ["total_submitted", "amount_paid", "patient_pays"])
        status = str(f.get("status", "")).upper()
        codes = [c for c in str(f.get("response_codes", "")).replace(" ", "").split(",") if c]
        unknown = [c for c in codes if c not in ref.RESPONSE_CODES]
        if not status:
            ok, detail = False, "no status"
        elif unknown:
            ok, detail = False, f"unknown response code {', '.join(unknown)}"
        elif status == "REJECTED" and not codes:
            ok, detail = False, "rejected with no reason code"
        elif status != "REJECTED" and codes:
            ok, detail = False, f"{status} but carries rejection code {', '.join(codes)}"
        elif status == "REJECTED" and paid not in (0.0, None):
            ok, detail = False, f"rejected, yet the plan pays {_fmt(paid)}"
        else:
            ok, detail = True, f"{status}" + (f" with {', '.join(codes)}" if codes else "")
        # Who pays what hinges on status, so a failure flags the amounts too.
        add("Status, codes and payment agree", ok, detail, ["status", "response_codes", "amount_paid", "patient_pays"])
    return out


def validate(doc_type: str, f: dict) -> list:
    """Flag every field that fails a check. Never changes a value. Works on any pipeline's
    output, OCR or LLM. Returns field flags; row flags go in each row's "_review"."""
    flags = []
    for group in ("medications", "line_items"):
        for row in f.get(group) or []:
            row.setdefault("_review", [])
    for c in checks(doc_type, f):
        if c["ok"]:
            continue
        if c["group"]:
            f[c["group"]][c["row"]]["_review"] += c["fields"]
        else:
            flags += c["fields"]
    return flags


def ocr_reference(doc, llm=None):
    # OCR the page twice (raw and noise-cleaned) and keep whichever parse fills more fields.
    parse = PARSERS[doc["doc_type"]]
    (raw_text, raw_ms), (clean_text, clean_ms) = run_ocr(doc["image_path"]), run_ocr(doc["image_path"], clean=True)
    start = time.perf_counter()
    f_raw, f_clean = parse(raw_text), parse(clean_text)
    f = f_clean if parsed_count(f_clean) > parsed_count(f_raw) else f_raw
    flags = _repair(doc["doc_type"], f) + validate(doc["doc_type"], f)
    return {"fields": f, "flags": flags, "latency_ms": raw_ms + clean_ms + (time.perf_counter() - start) * 1000,
            "cost_usd": 0.0}


def ocr_text_llm(doc, llm):
    text, ocr_ms = run_ocr(doc["image_path"])
    fields, ms, cost, _ = llm.extract(doc["doc_type"], ocr_text=text)
    return {"fields": fields, "flags": [], "latency_ms": ocr_ms + ms, "cost_usd": cost}


def vision_llm(doc, llm):
    fields, ms, cost, _ = llm.extract(doc["doc_type"], image_path=doc["image_path"])
    return {"fields": fields, "flags": [], "latency_ms": ms, "cost_usd": cost}


def vision_verified(doc, llm):
    """vision_llm's answer (same API call, served from cache in a combined run) plus the
    reference checks. Values are untouched; anything that fails a check is flagged for review."""
    out = vision_llm(doc, llm)
    start = time.perf_counter()
    out["flags"] = validate(doc["doc_type"], out["fields"])
    out["latency_ms"] += (time.perf_counter() - start) * 1000
    return out


PIPELINES = {"ocr_regex": ocr_regex, "ocr_reference": ocr_reference,
             "ocr_text_llm": ocr_text_llm, "vision_llm": vision_llm, "vision_verified": vision_verified}
LLM_PIPELINES = {"ocr_text_llm", "vision_llm", "vision_verified"}
