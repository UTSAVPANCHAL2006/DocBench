"""Tesseract OCR plus regex parsers that turn raw OCR text into fields.

The parsers key off the labels used on our templates (Rx pad, EMR printout,
wholesaler invoice) and the common variants of them ("M:", "Mitte", "Dispense";
"Rpt", "Repeats", "Refills"). That is a real limitation: an unseen template
needs new rules, which is exactly the maintenance cost the LLM pipelines avoid.
"""
import re
import time

import pytesseract
from PIL import Image, ImageFilter, ImageOps

_ocr_cache = {}

D = r"[0-9OolIS!]"  # a digit, or a letter OCR commonly confuses with one
DATE = (r"(\d{4}-\d{1,2}-\d{1,2}|\d{1,2}/\d{1,2}/\d{4}|\d{1,2}-[A-Za-z]{3}-\d{4}"
        r"|[A-Za-z]{3,9}\.?\s+\d{1,2},?\s+\d{4})")


def run_ocr(image_path: str, clean: bool = False):
    """Returns (text, ocr_ms). clean=True applies grayscale + median filter + autocontrast
    first (fixes speckle noise, but hurts skewed and fax pages). Cached so pipelines
    sharing OCR don't re-run it; the original OCR time is still charged to each of them."""
    key = (image_path, clean)
    if key not in _ocr_cache:
        start = time.perf_counter()
        img = Image.open(image_path)
        if clean:
            img = ImageOps.autocontrast(img.convert("L").filter(ImageFilter.MedianFilter(3)))
        text = pytesseract.image_to_string(img, config="--psm 6")
        _ocr_cache[key] = (text, (time.perf_counter() - start) * 1000)
    return _ocr_cache[key]


def parsed_count(fields: dict) -> int:
    """How many fields a parse filled in - used to pick between raw and cleaned OCR."""
    n = sum(1 for k, v in fields.items() if isinstance(v, str) and v)
    for key in ("medications", "line_items"):
        n += sum(sum(1 for v in item.values() if v) for item in fields.get(key, []))
    return n


def _find(pattern, text, flags=re.I | re.M):
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else ""


_DRUG_LINE = re.compile(rf"^\s*(?:\d\.\s*)?([A-Z][a-z]{{3,}})\s+({D}[0-9OolIS!.,]*\s*(?:mg|mcg|meg|g)\b)", re.M)


def parse_prescription(text: str) -> dict:
    fields = {
        "patient_name": _find(r"^\s*(?:Patient|Name)\s*[:;.]?\s*(.+?)\s*$", text),
        "patient_dob": _find(rf"(?:DOB|D0B|Birth\s*date|Date of Birth)\s*[:;.]?\s*{DATE}", text),
        "health_card": _find(rf"(?:HCN|Health\s*Card\s*#?)\s*[:;.]?\s*({D}{{4}}[\s-]?{D}{{3}}[\s-]?{D}{{3}}(?:[\s-]?[A-Z]{{2}})?)", text),
        "date_written": _find(rf"^\s*(?:.*\s)?Date(?!\s*of)\s*[:;.]?\s*{DATE}", text),
        "prescriber_name": _find(r"\b(Dr\.?\s+[A-Z][A-Za-z'\-]+\s+[A-Z][A-Za-z'\-]+)", text, re.M),
        "prescriber_license": _find(rf"CPSO\s*(?:#|No\.?)?\s*[:;]?\s*({D}{{5,6}})", text),
        "medications": [],
    }
    # Each drug line opens a block; sig / quantity / refills are read from the lines until the next drug.
    starts = list(_DRUG_LINE.finditer(text))
    for i, m in enumerate(starts):
        block = text[m.end(): starts[i + 1].start() if i + 1 < len(starts) else len(text)]
        refills = _find(rf"(?:Refills|Repeats|Rpt)\s*[:;.]?\s*x?\s*({D}+)", block)
        if not refills and re.search(r"No\s+refills", block, re.I):
            refills = "0"
        fields["medications"].append({
            "drug_name": m.group(1),
            "strength": m.group(2),
            "sig": _find(r"^\s*(?:Sig|Directions)\s*[:;.]?\s*(.+?)\s*$", block),
            "quantity": _find(rf"(?:Dispense|Mitte|Disp|Qty|Quantity|\bM)\s*[:;.]\s*#?\s*({D}+)", block),
            "refills": refills,
        })
    return fields


def parse_claim(text: str) -> dict:
    money = r"\$?\s*([\d,]+[.,]\d{2})"
    codes_block = text[text.lower().find("response codes"):] if "response codes" in text.lower() else ""
    drug = re.search(rf"Drug\s*[:;]\s*([A-Za-z][A-Za-z-]+)\s+({D}[0-9OolIS!.,]*\s*(?:MG|MCG|mg|mcg))", text)
    return {
        # stop at the "Group #:" column, not at a carrier named "... Group Benefits"
        "carrier": _find(r"Carrier\s*[:;]\s*(.+?)(?:\s{2,}|\s+Group\s*#|$)", text),
        "group_number": _find(rf"Group\s*#?\s*[:;]\s*({D}{{4,6}})", text),
        "patient_name": _find(r"Patient\s*[:;]\s*(.+?)(?:\s{2,}|\s+Cert\b|$)", text),
        "certificate_id": _find(rf"Cert(?:/ID)?\s*#?\s*[:;]\s*({D}{{6,10}}-?{D}{{0,2}})", text),
        "rx_number": _find(rf"Rx\s*#\s*[:;]\s*({D}{{5,8}})", text),
        "date_of_service": _find(rf"Date\s*of\s*Service\s*[:;]\s*{DATE}", text),
        "din": _find(rf"DIN\s*[:;]\s*({D}{{8}})", text),
        "drug_name": drug.group(1) if drug else "",
        "strength": drug.group(2) if drug else "",
        "quantity": _find(rf"Qty\s*[:;]\s*({D}+)", text),
        "days_supply": _find(rf"Days\s*Supply\s*[:;]\s*({D}+)", text),
        # The Total row shows submitted then adjudicated; the first figure is what was submitted.
        "total_submitted": _find(rf"^\s*Total\s+{money}", text),
        "amount_paid": _find(rf"Plan\s*Pays\s+{money}", text),
        "patient_pays": _find(rf"Patient\s*Pays\s+{money}", text),
        "status": _find(r"Status\s*[:;]\s*(PAID|REJECTED|ACCEPTED|PENDING)", text),
        "response_codes": ",".join(re.findall(r"^\s*([A-Z0-9]{2})\s+[A-Z][A-Za-z]", codes_block, re.M)),
        "trace_number": _find(rf"Trace\s*#\s*[:;]\s*({D}{{6,12}})", text),
    }


_ROW = re.compile(
    rf"^\s*{D}{{5,7}}\s+({D}{{8}}\s+)?(.+?)\s+({D}{{1,3}})\s+({D}{{1,3}})\s+({D}{{1,3}})\s+"
    rf"\$?({D}[0-9OolIS,]*[.,]\d{{2}})\s+\$?({D}[0-9OolIS,]*[.,]\d{{2}})\s*(T)?\s*$", re.M)


def parse_invoice(text: str) -> dict:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    # The first line can be a fax transmission header (often OCR'd as garbage); the supplier
    # name is the first line that reads like words rather than noise.
    def wordy(l):
        return "FROM:" not in l.upper() and len(re.findall(r"[A-Za-z]{3,}", l)) >= 2 and \
            sum(c.isalnum() or c == " " for c in l) / len(l) > 0.85
    first = next((l for l in lines if wordy(l)), "")
    fields = {
        "supplier": re.sub(r"\s+INVOICE\s*$", "", first, flags=re.I),
        "invoice_number": _find(r"Invoice\s*(?:No|#|Number)\.?\s*[:;]?\s*([0-9A-Z][0-9A-Z-]{4,})", text),
        "invoice_date": _find(rf"Invoice\s*Date\s*[:;]?\s*{DATE}", text),
        "account_number": _find(rf"Account\s*(?:No|#)\.?\s*[:;]?\s*({D}{{3}}-?{D}{{4}})", text),
        "po_number": _find(r"P\.?O\.?\s*(?:No|#)\.?\s*[:;]?\s*(PO-?\s?[0-9OolIS]{4,})", text),
        "subtotal": _find(r"Sub\s*total\s*[:;]?\s*\$?\s*([\d,]+[.,]\d{2})", text),
        "hst": _find(r"HST[^:\n]*[:;]\s*\$?\s*([\d,]+[.,]\d{2})", text),
        "total": _find(r"\bTotal\s*(?:Due)?\s*[:;]?\s*\$?\s*([\d,]+[.,]\d{2})", text),
        "line_items": [],
    }
    for m in _ROW.finditer(text):
        fields["line_items"].append({
            "din": (m.group(1) or "").strip(), "description": m.group(2), "qty_ordered": m.group(3),
            "qty_shipped": m.group(4), "unit_cost": m.group(6), "line_total": m.group(7),
            "taxable": bool(m.group(8)),
        })
    return fields
