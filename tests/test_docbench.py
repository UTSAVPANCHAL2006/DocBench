import random
import shutil

import pytest

from docbench import reference as ref
from docbench.evaluate import score_document, score_field
from docbench.generate import (degrade, fax_header, make_claim, make_invoice, make_prescription_emr,
                               make_prescription_pad, number_words)
from docbench.monitor import compare
from docbench.ocr import parse_claim, parse_invoice, parse_prescription


# --- evaluation -------------------------------------------------------------

@pytest.mark.parametrize("field,gt,pred,expected", [
    ("med1.strength", "500 mg", "500mg", (True, None)),                 # formatting is not an error
    ("date_written", "2026-03-14", "Mar 14, 2026", (True, None)),
    ("date_written", "2026-03-14", "14/03/2026", (True, None)),          # Canadian d/m/y
    ("date_written", "2026-03-14", "14-Mar-2026", (True, None)),         # EMR style
    ("total", "1234.50", "$1,234.50", (True, None)),
    ("patient_name", "Mei Khan", "KHAN, Mei", (True, None)),             # EMR surname-first
    ("prescriber_name", "Dr. Mei Chen", "Mei Chen, MD", (True, None)),
    ("health_card", "1234-567-890-AB", "1234567890AB", (True, None)),
    ("med1.strength", "0.5 mg", "5 mg", (False, "numeric_mismatch")),   # 10x dose error
    ("med1.quantity", "30", "", (False, "missing")),
    ("med1.drug_name", "Atorvastatin", "Atorvastatn", (False, "near_miss")),
    ("med1.drug_name", "Hydroxyzine", "Hydralazine", (False, "wrong_value")),  # look-alike drug swap
    ("health_card", "", "1234-567-890-AB", (False, "hallucinated")),
    ("patient_dob", "1960-01-10", "1960-10-01", (False, "date_mismatch")),
    ("med1.drug_name", "Atorvastatin", "Lipitor", (True, None)),         # brand = generic
    ("med1.drug_name", "Atorvastatin", "APO-ATORVASTATIN", (True, None)),  # manufacturer-prefixed generic
    ("med1.drug_name", "Celexa", "Celebrex", (False, "wrong_value")),    # brand look-alikes are different drugs
    ("response_codes", "D7,LO", "LO, D7", (True, None)),
    ("response_codes", "D7", "", (False, "missing")),
    ("status", "REJECTED", "PAID", (False, "wrong_value")),
    ("med1.strength", "10 mg", "10 mg tablet", (True, None)),
    ("prescriber_license", "49862", "CPSO #49862", (True, None)),
    ("med1.sig", "1 cap PO BID", "Sig: 1 cap PO BID", (True, None)),           # label isn't part of the sig
    ("drug_name", "Hydralazine", "HYDRALAZINE 25MG TAB", (True, None)),      # strength/form appended
    ("drug_name", "Prednisone", "PREDNISONE SMG TAB", (True, None)),
    ("drug_name", "Hydralazine", "HYDROXYZINE 25MG TAB", (False, "wrong_value")),
    ("med1.strength", "10 mg", "100 mg tablet", (False, "numeric_mismatch")),
])
def test_score_field(field, gt, pred, expected):
    assert score_field(field, gt, pred) == expected


def _invoice(lines):
    return {"doc_type": "invoice", "fields": {"supplier": "A", "invoice_number": "4400001", "invoice_date": "2026-01-01",
                                              "account_number": "100-2000", "po_number": "PO-12345",
                                              "subtotal": "6.00", "hst": "0.00", "total": "6.00", "line_items": lines}}


def _line(i):
    return {"din": f"0000000{i}", "qty_ordered": str(i), "qty_shipped": str(i), "unit_cost": "1.00", "line_total": f"{i}.00"}


def test_extra_invoice_line_is_hallucinated():
    doc = _invoice([_line(1)])
    scored = score_document(doc, {"fields": {**doc["fields"], "line_items": [_line(1), _line(2)]}})
    assert scored["line2.din"]["category"] == "hallucinated"
    assert all(v["correct"] for k, v in scored.items() if not k.startswith("line2"))


def test_skipped_invoice_row_only_costs_that_row():
    lines = [_line(i) for i in (1, 2, 3)]
    doc = _invoice(lines)
    scored = score_document(doc, {"fields": {**doc["fields"], "line_items": [{**lines[1], "_review": ["din"]}, lines[2]]}})
    assert sorted(k for k, v in scored.items() if not v["correct"]) == [f"line1.{k}" for k in
                                                                        ("din", "line_total", "qty_ordered", "qty_shipped", "unit_cost")]
    assert scored["line2.din"]["flagged"]          # the flag followed its row after alignment


def test_blank_absent_field_is_not_scored():
    doc = {"doc_type": "prescription", "fields": {"patient_name": "Mei Chen", "health_card": "", "medications": []}}
    scored = score_document(doc, {"fields": {"patient_name": "Mei Chen"}})
    assert "health_card" not in scored and scored["patient_name"]["correct"]


# --- reference repair -------------------------------------------------------

def test_match_drug_corrects_clear_typo():
    assert ref.match_drug("Atorvastatn") == ("Atorvastatin", False)


def test_match_drug_refuses_ambiguous_lookalike():
    # Equally far from Hydroxyzine and Hydralazine: must flag, not guess.
    _, review = ref.match_drug("Hydr0zine")
    assert review


def test_brand_and_prefixed_names_resolve_to_generic():
    assert ref.match_drug("Lipitor") == ("Atorvastatin", False)
    assert ref.match_drug("TEVA-SERTRALINE") == ("Sertraline", False)
    assert ref.match_drug("Ce1exa") == ("Citalopram", False)          # OCR typo of a brand name
    assert ref.canonical_drug("Ce1exa") == "Ce1exa"                     # but scoring never auto-forgives typos


def test_strength_and_sig_repair():
    assert ref.normalize_strength("5OOmg") == "500 mg"
    assert ref.correct_sig("I tab P0 BlD") == "1 tab PO BID"
    assert ref.correct_sig("1-2. tabs PO Q4-6H") == "1-2 tabs PO Q4-6H"
    assert ref.correct_sig("Take 1 tablet by mouth twlce daily") == "Take 1 tablet by mouth twice daily"
    assert ref.expand_sig("1 tab PO BID") == "1 tablet by mouth twice daily"
    assert ref.sig_is_plausible("Sig: Take 1 tablet by mouth twice daily,")
    assert not ref.sig_is_plausible("1 tab PO Q4H5") and not ref.sig_is_plausible("1/2 fab po daily")


def test_repair_din():
    din = ref.CATALOGUE[0]["din"]
    assert ref.repair_din(din) == (din, False)
    assert ref.repair_din(din.replace("0", "O", 1)) == (din, False)   # O->0 is a deterministic fix
    one_off = din[:-1] + str((int(din[-1]) + 1) % 10)
    _, review = ref.repair_din(one_off)
    assert review                                                       # corrected guesses are always flagged


# --- parsers ----------------------------------------------------------------

def test_parse_emr_prescription_with_two_meds():
    text = ("Lakeshore Health Group PRESCRIPTION\n440 Queen St E, Ottawa Date: 14-Mar-2026\n"
            "Patient: KHAN, Mei\nDOB: 1980-02-03\nHCN: 1234-567-890-AB\n"
            "1. Warfarin 2.5 mg tablet\nSig: Take 1 tablet by mouth once daily\nDispense: 30 (thirty) tablets Refills: 2\n"
            "2. Ramipril 5 mg capsule\nSig: Take 1 capsule by mouth twice daily\nDispense: 60 (sixty) capsules Refills: 0\n"
            "Dr. Omar Khan, MD CPSO #54321\n")
    f = parse_prescription(text)
    assert (f["patient_name"], f["patient_dob"], f["health_card"], f["date_written"]) == \
           ("KHAN, Mei", "1980-02-03", "1234-567-890-AB", "14-Mar-2026")
    assert (f["prescriber_name"], f["prescriber_license"]) == ("Dr. Omar Khan", "54321")
    assert f["medications"] == [
        {"drug_name": "Warfarin", "strength": "2.5 mg", "sig": "Take 1 tablet by mouth once daily", "quantity": "30", "refills": "2"},
        {"drug_name": "Ramipril", "strength": "5 mg", "sig": "Take 1 capsule by mouth twice daily", "quantity": "60", "refills": "0"}]


def test_parse_pad_shorthand():
    text = "Name: Chloe Wong\nDate: 05/06/2026\nRx\nPrednisone 5mg tab\nSig: 1 tab PO daily\nMitte: #21  No refills\n"
    med = parse_prescription(text)["medications"][0]
    assert (med["strength"], med["quantity"], med["refills"]) == ("5mg", "21", "0")


def test_parse_invoice_rows_backorders_and_totals():
    text = ("Jun 24 2026 13:05 FROM: Northbridge FAX (613) 555-2272 P.1/1\n"
            "Northbridge Pharma Distribution INVOICE\nShip To: Invoice No: 4954426\nInvoice Date: 2026-07-03\n"
            "Account No: 817-6108\nPO No: PO-14396\n"
            "672622 00136160 CETIRIZINE 10MG TAB 30 7 7 0 23.37 163.59 T\n"
            "485640 08136896 PREDNISONE 50MG TAB 100 1 0 1 103.31 0.00\n"
            "235837 ADHESIVE BANDAGES ASSORTED 30 3 3 0 24.48 73.44 T\n"
            "Subtotal: 237.03\nHST 13%: 30.82\nTotal Due: $ 267.85\n")
    f = parse_invoice(text)
    assert f["supplier"] == "Northbridge Pharma Distribution"
    assert (f["invoice_number"], f["account_number"], f["po_number"]) == ("4954426", "817-6108", "PO-14396")
    assert (f["subtotal"], f["hst"], f["total"]) == ("237.03", "30.82", "267.85")
    assert [(l["din"], l["qty_shipped"], l["taxable"]) for l in f["line_items"]] == \
           [("00136160", "7", True), ("08136896", "0", False), ("", "3", True)]


def test_parse_claim_rejected():
    text = ("Bloor Street Pharmacy CLAIM ADJUDICATION RESPONSE\n"
            "Carrier: Trillium Group Benefits Group #: 48213\n"
            "Patient: CHEN, Mei Cert/ID #: 30019284-01\n"
            "Rx #: 1234567 Date of Service: 14-Mar-2026\n"
            "DIN: 02230730 Drug: LIPITOR 20MG TAB\n"
            "Qty: 30 Days Supply: 30\n"
            "Total 58.19 58.19\nPlan Pays 0.00\nPatient Pays 58.19\n"
            "Status: REJECTED Trace #: 884213907\nResponse Codes:\n D7 Refill too soon\n 57 SSC error\n")
    f = parse_claim(text)
    assert (f["carrier"], f["patient_name"], f["certificate_id"]) == ("Trillium Group Benefits", "CHEN, Mei", "30019284-01")
    assert (f["drug_name"], f["strength"], f["din"]) == ("LIPITOR", "20MG", "02230730")
    assert (f["total_submitted"], f["amount_paid"], f["patient_pays"]) == ("58.19", "0.00", "58.19")
    assert (f["status"], f["response_codes"], f["trace_number"]) == ("REJECTED", "D7,57", "884213907")


def test_monitor_flags_regressions_and_passes_steady_runs():
    base = {"critical_acc": "0.90", "silent_wrong": "20", "p50_ms": "400", "cost_per_1k": "10.00", "failed_calls": "0"}
    assert compare(base, dict(base)) == []
    worse = {**base, "critical_acc": "0.85", "silent_wrong": "30", "p50_ms": "900", "cost_per_1k": "15.00"}
    assert len(compare(base, worse)) == 4


# --- generator --------------------------------------------------------------

@pytest.mark.parametrize("maker", [make_prescription_pad, make_prescription_emr])
def test_prescriptions_are_deterministic_and_complete(maker):
    a, b = maker(random.Random(1))[1], maker(random.Random(1))[1]
    assert a == b
    assert a["medications"] and all(a["medications"][0].values())
    assert a["prescriber_license"] and a["date_written"]   # CPSO-required elements


def test_invoice_arithmetic_and_tax():
    for seed in range(20):
        inv = make_invoice(random.Random(seed))[1]
        lines = inv["line_items"]
        assert all(abs(int(l["qty_shipped"]) * float(l["unit_cost"]) - float(l["line_total"])) < 0.01 for l in lines)
        taxable = sum(float(l["line_total"]) for l in lines if l["taxable"])
        assert float(inv["hst"]) == round(taxable * ref.HST_RATE, 2)
        assert abs(float(inv["subtotal"]) + float(inv["hst"]) - float(inv["total"])) < 0.01


def test_claim_arithmetic_and_codes():
    for seed in range(30):
        c = make_claim(random.Random(seed))[1]
        assert abs(float(c["amount_paid"]) + float(c["patient_pays"]) - float(c["total_submitted"])) < 0.01
        codes = [x for x in c["response_codes"].split(",") if x]
        assert (c["status"] == "REJECTED") == bool(codes)
        assert all(x in ref.RESPONSE_CODES for x in codes)
        if c["status"] == "REJECTED":
            assert c["amount_paid"] == "0.00"


def test_number_words():
    assert [number_words(n) for n in (14, 21, 60, 100)] == ["fourteen", "twenty-one", "sixty", "one hundred"]


def test_degradations_keep_image_valid():
    img = fax_header(make_prescription_pad(random.Random(3))[0], random.Random(0), "Clinic")
    for kind in ["clean", "skew", "blur", "noise", "fax", "low_res"]:
        out = degrade(img, kind, random.Random(0))
        assert out.mode == "RGB" and out.width >= img.width


@pytest.mark.skipif(not shutil.which("tesseract"), reason="tesseract not installed")
@pytest.mark.parametrize("maker,doc_type", [(make_invoice, "invoice"), (make_claim, "claim")])
def test_ocr_end_to_end_on_clean_print(tmp_path, maker, doc_type):
    from docbench.pipelines import ocr_reference
    img, gt, _ = maker(random.Random(5))
    path = tmp_path / "doc.png"
    img.save(path)
    doc = {"doc_id": "t", "doc_type": doc_type, "image_path": str(path), "fields": gt}
    scored = score_document(doc, ocr_reference(doc))
    assert sum(v["correct"] for v in scored.values()) / len(scored) > 0.9


# --- validation layer on LLM-style output -------------------------------------

def test_validate_flags_without_changing_values():
    from docbench.pipelines import validate
    claim = {"din": ref.CATALOGUE[0]["din"], "drug_name": f"{ref.CATALOGUE[0]['drug'].upper()} TAB",
             "strength": ref.CATALOGUE[0]["strength"], "total_submitted": "100.00", "amount_paid": "100.00",
             "patient_pays": "20.00", "status": "PAID", "response_codes": ""}
    before = dict(claim)
    flags = validate("claim", claim)
    assert claim == before                                         # flag-only: nothing rewritten
    assert {"amount_paid", "patient_pays", "total_submitted"} <= set(flags)  # 100 + 20 != 100
    assert "din" not in flags and "drug_name" not in flags


def test_validate_invoice_line_math_and_unknown_din():
    from docbench.pipelines import validate
    good = {"din": ref.CATALOGUE[1]["din"], "qty_ordered": "2", "qty_shipped": "2", "unit_cost": "5.00", "line_total": "10.00"}
    bad = {"din": "99999999", "qty_ordered": "2", "qty_shipped": "2", "unit_cost": "5.00", "line_total": "100.00"}
    inv = {"subtotal": "110.00", "hst": "0.00", "total": "110.00", "line_items": [good, bad]}
    validate("invoice", inv)
    assert good["_review"] == []
    assert set(bad["_review"]) == {"din", "qty_ordered", "qty_shipped", "unit_cost", "line_total"}
