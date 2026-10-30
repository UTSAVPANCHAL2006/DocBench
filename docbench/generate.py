"""Render synthetic Canadian (Ontario) pharmacy documents with ground-truth JSON.

Three styles, modelled on what an independent pharmacy actually receives:
  pad      handwritten prescription on a pre-printed prescriber pad with a
           security watermark; Latin sig shorthand ("1 tab PO BID", "M: 30", "Rpt x2")
  emr      prescription printed from a clinic EMR: "SURNAME, Given", health card
           number, numbered medications, plain-English sig, "Dispense: 60 (sixty)"
  invoice  wholesaler invoice: account/PO numbers, ordered/shipped/backordered
           quantities, zero-rated Rx lines vs. HST-taxable OTC/supply lines
  claim    third-party claim adjudication response printed by the pharmacy system:
           submitted vs. adjudicated amounts, plan/patient split, PAID/REJECTED, response codes

Content follows the CPSO "Prescribing Drugs" policy (prescriber name, signature,
CPSO number, practice address, patient, drug, strength, quantity, directions,
full date, refills). Every person, clinic, supplier, health card number and DIN
is fictional. Each document gets exactly one degradation, assigned round-robin;
"fax" pages also get a fax transmission header, as real faxed scripts do.
"""
import io
import json
import random
from datetime import date, datetime, time, timedelta

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from . import reference as ref
from .config import DATA_DIR, DEGRADATIONS, DOCS_DIR, GT_DIR

LETTER = (1275, 1650)  # 8.5 x 11 in at 150 dpi
PAD = (850, 1100)      # 4.25 x 5.5 in prescription pad at 200 dpi

_SUPP = "/System/Library/Fonts/Supplemental/"
SANS = [_SUPP + "Arial.ttf", "/System/Library/Fonts/Helvetica.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
SANS_BOLD = [_SUPP + "Arial Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
# Printouts use the bold cut: regular Courier is a hairline face that a fax wipes out entirely,
# which would make the page unreadable to a person too, and so an unfair test.
MONO = [_SUPP + "Courier New Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"]
_SUPP_MONO_BOLD = [_SUPP + "Courier New Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"]
HAND = ["/System/Library/Fonts/Noteworthy.ttc", "/System/Library/Fonts/MarkerFelt.ttc"]

FIRST = ["Priya", "Liam", "Olivia", "Arjun", "Emma", "Noah", "Mei", "Lucas", "Fatima", "Ethan",
         "Sofia", "Wei", "Aisha", "Gabriel", "Chloe", "Ravi", "Hannah", "Omar", "Isabelle", "Jun"]
LAST = ["Tremblay", "Singh", "Nguyen", "MacDonald", "Patel", "Roy", "Chen", "Gagnon", "Khan", "Wilson",
        "Bouchard", "Kaur", "Lee", "Martin", "Ahmed", "Fraser", "Leblanc", "Wong", "Campbell", "Das"]
CLINICS = ["Maplewood Family Clinic", "Riverside Medical Centre", "Lakeshore Health Group", "Northgate Family Health Team"]
SUPPLIERS = ["Northbridge Pharma Distribution", "Cedarline Medical Supply", "Great Lakes Rx Wholesale"]
PHARMACIES = ["Bloor Street Pharmacy", "Harbourview Pharmacy", "Prairie Lane Pharmacy"]
STREETS = ["King St W", "Queen St E", "Main St N", "Dundas St", "Bathurst St", "Lakeshore Blvd"]
CITIES = [("Toronto", "M5V"), ("Hamilton", "L8P"), ("Mississauga", "L5B"), ("Ottawa", "K1P")]

_ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen " \
        "sixteen seventeen eighteen nineteen".split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def number_words(n: int) -> str:
    if n < 20:
        return _ONES[n]
    if n < 100:
        return _TENS[n // 10] + ("" if n % 10 == 0 else "-" + _ONES[n % 10])
    return "one hundred" if n == 100 else str(n)


def _font(candidates, size):
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _rand_date(rng, start: date, end: date) -> date:
    return start + timedelta(days=rng.randint(0, (end - start).days))


def _address(rng):
    city, fsa = rng.choice(CITIES)
    return f"{rng.randint(10, 999)} {rng.choice(STREETS)}, {city}, ON {fsa} {rng.randint(1, 9)}{rng.choice('ABCEGHJ')}{rng.randint(1, 9)}"


def _phone(rng):
    return f"({rng.choice([416, 647, 905, 613])}) 555-{rng.randint(1000, 9999)}"


def _health_card(rng):
    d = "".join(str(rng.randint(0, 9)) for _ in range(10))
    return f"{d[:4]}-{d[4:7]}-{d[7:]}-{rng.choice('ABCDEFGHJK')}{rng.choice('ABCDEFGHJK')}"


def _signature(d, x, y, rng, colour=(20, 30, 110)):
    pts = [(x + i * 11, y + rng.randint(-22, 22)) for i in range(26)]
    d.line(pts, fill=colour, width=3)


def _watermark(img, text="ORIGINAL"):
    """Faint diagonal security pattern, as on tamper-resistant prescription pads."""
    layer = Image.new("L", (img.width * 2, img.height * 2), 0)
    ld = ImageDraw.Draw(layer)
    f = _font(SANS_BOLD, 36)
    for yy in range(0, layer.height, 110):
        for xx in range(-200 + (yy // 110 % 2) * 120, layer.width, 260):
            ld.text((xx, yy), text, font=f, fill=255)
    layer = layer.rotate(30).crop((img.width // 2, img.height // 2, img.width // 2 + img.width, img.height // 2 + img.height))
    tint = Image.new("RGB", img.size, (228, 232, 240))
    return Image.composite(tint, img, layer)


def _meds(rng, n):
    """n distinct drugs, with look-alike pairs sometimes forced together on one script."""
    drugs = rng.sample(ref.DRUGS, n)
    if n >= 2 and rng.random() < 0.3:
        a, b = rng.choice(ref.LOOK_ALIKE)
        drugs[:2] = [ref.DRUG_BY_NAME[a.lower()], ref.DRUG_BY_NAME[b.lower()]]
    return drugs


def _written_name(rng, drug, p_brand):
    """Prescribers write the brand name a fair share of the time ("Lipitor" for atorvastatin)."""
    return rng.choice(drug["brands"]) if rng.random() < p_brand else drug["name"]


def _person(rng):
    return rng.choice(FIRST), rng.choice(LAST)


def make_prescription_pad(rng):
    W, H = PAD
    img = Image.new("RGB", PAD, (252, 252, 248))
    img = _watermark(img)
    d = ImageDraw.Draw(img)
    hand, hand_small = _font(HAND, 34), _font(HAND, 30)
    sans, sans_b, small = _font(SANS, 22), _font(SANS_BOLD, 28), _font(SANS, 18)
    ink = (20, 30, 110)

    pf, pl = _person(rng)
    df, dl = _person(rng)
    clinic, license_no = rng.choice(CLINICS), str(rng.randint(10000, 129999))
    show_dob, show_hcn = rng.random() < 0.6, rng.random() < 0.4
    date_fmt = rng.choice(["%Y-%m-%d", "%d/%m/%Y", "%b %d, %Y", "%d-%b-%Y"])
    meds_src = _meds(rng, rng.choice([1, 1, 2]))

    gt = {"patient_name": f"{pf} {pl}",
          "patient_dob": _rand_date(rng, date(1940, 1, 1), date(2010, 12, 31)).isoformat() if show_dob else "",
          "health_card": _health_card(rng) if show_hcn else "",
          "date_written": _rand_date(rng, date(2026, 1, 1), date(2026, 10, 1)).isoformat(),
          "prescriber_name": f"Dr. {df} {dl}", "prescriber_license": license_no, "medications": []}

    # pre-printed header
    d.text((50, 40), f"Dr. {df} {dl}, MD CCFP", font=sans_b, fill="black")
    d.text((50, 80), clinic, font=sans, fill="black")
    d.text((50, 108), _address(rng), font=small, fill="black")
    d.text((50, 132), f"Tel {_phone(rng)}  ·  Fax {_phone(rng)}", font=small, fill="black")
    d.text((50, 156), f"CPSO #{license_no}", font=small, fill="black")
    d.line((50, 190, W - 50, 190), fill="black", width=2)

    y = 215
    rows = [("Name:", gt["patient_name"]), ("Address:", _address(rng).split(",")[0])]
    if show_dob:
        rows.append(("DOB:", date.fromisoformat(gt["patient_dob"]).strftime(date_fmt)))
    if show_hcn:
        rows.append(("Health Card #:", gt["health_card"]))
    rows.append(("Date:", date.fromisoformat(gt["date_written"]).strftime(date_fmt)))
    for label, value in rows:
        d.text((50, y + 6), label, font=sans, fill="black")
        lx = 50 + int(d.textlength(label, font=sans)) + 14
        d.line((lx, y + 34, W - 50, y + 34), fill=(150, 150, 150), width=1)
        d.text((lx + rng.randint(0, 12), y + rng.randint(-4, 2)), value, font=hand_small, fill=ink)
        y += 52

    d.text((50, y + 10), "Rx", font=_font(SANS_BOLD, 64), fill="black")
    y += 95
    for drug in meds_src:
        strength = rng.choice(drug["strengths"])
        unit = ref.SIG_UNIT[drug["form"]]
        sig = rng.choice(ref.SIG_TEMPLATES).format(u=unit)
        qty, refills = rng.choice([14, 21, 28, 30, 60, 90, 100]), rng.choice([0, 0, 1, 2, 3, 5])
        name = _written_name(rng, drug, 0.35)
        gt["medications"].append({"drug_name": name, "strength": strength, "sig": sig,
                                  "quantity": str(qty), "refills": str(refills)})
        written_strength = strength.replace(" ", "") if rng.random() < 0.5 else strength
        qty_txt = rng.choice([f"M: {qty}", f"Mitte: #{qty}", f"Disp: {qty}"])
        rpt_txt = ("No refills" if rng.random() < 0.5 else "Rpt x0") if refills == 0 else rng.choice([f"Rpt x{refills}", f"Refills: {refills}"])
        for line in (f"{name} {written_strength} {unit}", f"Sig: {sig}", f"{qty_txt}    {rpt_txt}"):
            d.text((70 + rng.randint(-8, 8), y + rng.randint(-3, 3)), line, font=hand, fill=ink)
            y += 50
        y += 18

    d.text((50, H - 150), "[  ] Do not substitute", font=small, fill="black")
    _signature(d, W - 380, H - 175, rng)
    d.line((W - 400, H - 135, W - 50, H - 135), fill="black", width=1)
    d.text((W - 400, H - 128), "Prescriber signature", font=small, fill="black")
    d.text((50, H - 60), "This prescription is void if altered. Not valid if photocopied.", font=_font(SANS, 15), fill=(90, 90, 90))
    return img, gt, {"style": "pad", "date_format": date_fmt, "clinic": clinic}


def make_prescription_emr(rng):
    W, H = LETTER
    img = Image.new("RGB", LETTER, "white")
    d = ImageDraw.Draw(img)
    title, body, bold, mono = _font(SANS_BOLD, 34), _font(SANS, 24), _font(SANS_BOLD, 24), _font(MONO, 24)

    pf, pl = _person(rng)
    df, dl = _person(rng)
    clinic, license_no = rng.choice(CLINICS), str(rng.randint(10000, 129999))
    date_fmt = rng.choice(["%Y-%m-%d", "%d-%b-%Y"])
    meds_src = _meds(rng, rng.choice([1, 2, 2, 3]))
    gt = {"patient_name": f"{pf} {pl}",
          "patient_dob": _rand_date(rng, date(1940, 1, 1), date(2010, 12, 31)).isoformat(),
          "health_card": _health_card(rng),
          "date_written": _rand_date(rng, date(2026, 1, 1), date(2026, 10, 1)).isoformat(),
          "prescriber_name": f"Dr. {df} {dl}", "prescriber_license": license_no, "medications": []}
    fmt = lambda iso: date.fromisoformat(iso).strftime(date_fmt)

    d.text((80, 70), clinic, font=title, fill="black")
    d.text((80, 115), _address(rng), font=body, fill="black")
    d.text((80, 147), f"Tel {_phone(rng)}    Fax {_phone(rng)}", font=body, fill="black")
    d.text((W - 380, 70), "PRESCRIPTION", font=title, fill="black")
    d.text((W - 380, 115), f"Date: {fmt(gt['date_written'])}", font=body, fill="black")
    d.line((80, 195, W - 80, 195), fill="black", width=2)

    y = 225
    for label, value in [("Patient:", f"{pl.upper()}, {pf}"), ("DOB:", fmt(gt["patient_dob"])),
                         ("HCN:", gt["health_card"]), ("Address:", _address(rng))]:
        d.text((80, y), label, font=bold, fill="black")
        d.text((250, y), value, font=body, fill="black")
        y += 38
    d.line((80, y + 15, W - 80, y + 15), fill=(160, 160, 160), width=1)
    y += 45

    for i, drug in enumerate(meds_src, 1):
        strength = rng.choice(drug["strengths"])
        sig = rng.choice(ref.SIG_TEMPLATES_EMR).format(f=drug["form"])
        qty, refills = rng.choice([14, 21, 28, 30, 60, 90, 100]), rng.choice([0, 1, 2, 3, 5])
        name = _written_name(rng, drug, 0.2)
        gt["medications"].append({"drug_name": name, "strength": strength, "sig": sig,
                                  "quantity": str(qty), "refills": str(refills)})
        d.text((80, y), f"{i}. {name} {strength} {drug['form']}", font=bold, fill="black")
        d.text((120, y + 38), f"Sig: {sig}", font=mono, fill="black")
        d.text((120, y + 76), f"Dispense: {qty} ({number_words(qty)}) {drug['form']}s    Refills: {refills}", font=mono, fill="black")
        y += 140

    y = max(y + 40, 1150)
    _signature(d, 90, y + 30, rng, colour=(10, 10, 10))
    d.line((80, y + 70, 520, y + 70), fill="black", width=1)
    d.text((80, y + 80), f"Dr. {df} {dl}, MD    CPSO #{license_no}", font=body, fill="black")
    d.text((80, H - 90), "Generated by clinic EMR. Original retained on patient chart.", font=_font(SANS, 18), fill=(90, 90, 90))
    return img, gt, {"style": "emr", "date_format": date_fmt, "clinic": clinic}


def make_invoice(rng):
    W, H = LETTER
    lines = []
    for it in rng.sample(ref.CATALOGUE, rng.randint(3, 6)):
        form = "TAB" if it["form"] == "tablet" else "CAP"
        prefix = rng.choice(ref.GENERIC_PREFIXES) if rng.random() < 0.5 else ""
        lines.append({"din": it["din"], "description": f"{prefix}{it['drug'].upper()} {it['strength'].replace(' ', '').upper()} {form} {it['pack']}",
                      "taxable": False, "unit": round(rng.uniform(4, 240), 2)})
    for it in rng.sample(ref.OTC_ITEMS, rng.randint(0, 3)):
        lines.append({"din": ref.OTC_DINS.get(it["description"], ""), "description": it["description"],
                      "taxable": True, "unit": round(rng.uniform(2, 25), 2)})
    rng.shuffle(lines)
    for l in lines:
        ordered = rng.randint(1, 12)
        shipped = 0 if rng.random() < 0.15 else ordered  # backordered lines ship nothing and bill nothing
        l.update(qty_ordered=str(ordered), qty_shipped=str(shipped), unit_cost=f"{l.pop('unit'):.2f}")
        l["line_total"] = f"{shipped * float(l['unit_cost']):.2f}"
    rx_sum = sum(float(l["line_total"]) for l in lines if not l["taxable"])
    tax_sum = sum(float(l["line_total"]) for l in lines if l["taxable"])
    hst = round(tax_sum * ref.HST_RATE, 2)
    date_fmt = rng.choice(["%Y-%m-%d", "%d/%m/%Y", "%b %d, %Y"])
    supplier = rng.choice(SUPPLIERS)
    gt = {"supplier": supplier, "invoice_number": str(rng.randint(4000000, 4999999)),
          "invoice_date": _rand_date(rng, date(2026, 1, 1), date(2026, 10, 1)).isoformat(),
          "account_number": f"{rng.randint(100, 999)}-{rng.randint(1000, 9999)}",
          "po_number": f"PO-{rng.randint(10000, 99999)}",
          "subtotal": f"{rx_sum + tax_sum:.2f}", "hst": f"{hst:.2f}", "total": f"{rx_sum + tax_sum + hst:.2f}",
          "line_items": [{k: l[k] for k in ("din", "description", "qty_ordered", "qty_shipped", "unit_cost", "line_total", "taxable")} for l in lines]}

    img = Image.new("RGB", LETTER, "white")
    d = ImageDraw.Draw(img)
    title, body, small, bold = _font(SANS_BOLD, 38), _font(SANS, 22), _font(SANS, 19), _font(SANS_BOLD, 20)
    d.text((60, 60), supplier, font=title, fill="black")
    d.text((60, 110), "2250 Meadowpine Blvd, Mississauga, ON L5N 6S2", font=small, fill="black")
    d.text((60, 136), f"Customer Service {_phone(rng)}  ·  GST/HST Reg. No. {rng.randint(10000, 99999)} {rng.randint(1000, 9999)} RT0001",
           font=small, fill="black")
    d.text((W - 300, 60), "INVOICE", font=title, fill="black")
    right = [("Invoice No:", gt["invoice_number"]), ("Invoice Date:", date.fromisoformat(gt["invoice_date"]).strftime(date_fmt)),
             ("Account No:", gt["account_number"]), ("PO No:", gt["po_number"]), ("Page:", "1 of 1")]
    for i, (k, v) in enumerate(right):
        d.text((W - 420, 200 + i * 32), f"{k} {v}", font=body, fill="black")
    d.text((60, 200), "Ship To:", font=bold, fill="black")
    d.text((60, 232), rng.choice(PHARMACIES), font=body, fill="black")
    d.text((60, 264), _address(rng), font=small, fill="black")

    cols = [("Item #", 60), ("DIN", 165), ("Description", 290), ("Ord", 780), ("Ship", 850), ("B/O", 925),
            ("Unit Price", 990), ("Extension", 1120)]
    y = 400
    for name, x in cols:
        d.text((x, y), name, font=bold, fill="black")
    d.line((60, y + 34, W - 40, y + 34), fill="black", width=2)
    y += 50
    for l in lines:
        bo = int(l["qty_ordered"]) - int(l["qty_shipped"])
        vals = [str(rng.randint(100000, 999999)), l["din"], l["description"], l["qty_ordered"], l["qty_shipped"],
                str(bo), l["unit_cost"], l["line_total"]]
        for (_, x), v in zip(cols, vals):
            d.text((x, y), v, font=small, fill="black")
        if l["taxable"]:
            d.text((1235, y), "T", font=small, fill="black")
        y += 40
    d.line((60, y + 5, W - 40, y + 5), fill="black", width=2)
    y += 25
    d.text((60, y), "T = taxable item. Prescription drugs are zero-rated.", font=small, fill="black")
    for label, val, f in [("Rx (zero-rated):", f"{rx_sum:.2f}", body), ("Taxable items:", f"{tax_sum:.2f}", body),
                          ("Subtotal:", gt["subtotal"], body), ("HST 13%:", gt["hst"], body), ("Total Due: $", gt["total"], bold)]:
        d.text((820, y), f"{label} {val}", font=f, fill="black")
        y += 34
    d.text((60, H - 80), "Payment terms: Net 30. Returns require RA number within 30 days.", font=small, fill=(80, 80, 80))
    return img, gt, {"style": "invoice", "date_format": date_fmt, "clinic": supplier}


def make_claim(rng):
    """Adjudication response as printed from pharmacy management software after a
    third-party claim: submitted vs. adjudicated amounts, plan/patient split, status, codes."""
    W, H = LETTER
    drug = rng.choice(ref.DRUGS)
    strength = rng.choice(drug["strengths"])
    din = next(c["din"] for c in ref.CATALOGUE if c["drug"] == drug["name"] and c["strength"] == strength)
    name = _written_name(rng, drug, 0.4)
    pf, pl = _person(rng)
    qty = rng.choice([14, 28, 30, 60, 90, 100])
    cost = round(rng.uniform(6, 180), 2)
    total = round(cost + ref.DISPENSING_FEE, 2)
    rejected = rng.random() < 0.3
    codes = sorted(rng.sample(list(ref.RESPONSE_CODES), rng.choice([1, 1, 2]))) if rejected else []
    coinsurance = rng.choice([0.0, 0.1, 0.2])
    patient_pays = total if rejected else round(total * coinsurance, 2)
    gt = {"carrier": rng.choice(ref.CARRIERS), "group_number": str(rng.randint(10000, 99999)),
          "patient_name": f"{pf} {pl}", "certificate_id": f"{rng.randint(10000000, 99999999)}-0{rng.randint(1, 3)}",
          "rx_number": str(rng.randint(1000000, 9999999)),
          "date_of_service": _rand_date(rng, date(2026, 1, 1), date(2026, 10, 1)).isoformat(),
          "din": din, "drug_name": name, "strength": strength, "quantity": str(qty), "days_supply": str(rng.choice([7, 14, 30, 90])),
          "total_submitted": f"{total:.2f}", "amount_paid": f"{total - patient_pays:.2f}", "patient_pays": f"{patient_pays:.2f}",
          "status": "REJECTED" if rejected else "PAID", "response_codes": ",".join(codes),
          "trace_number": str(rng.randint(100000000, 999999999))}
    date_fmt = rng.choice(["%Y-%m-%d", "%d-%b-%Y"])

    img = Image.new("RGB", LETTER, "white")
    d = ImageDraw.Draw(img)
    mono, mono_b, title = _font(MONO, 25), _font(_SUPP_MONO_BOLD, 25), _font(SANS_BOLD, 32)
    d.text((70, 60), rng.choice(PHARMACIES), font=title, fill="black")
    d.text((70, 105), _address(rng), font=_font(SANS, 20), fill="black")
    d.text((W - 560, 60), "CLAIM ADJUDICATION RESPONSE", font=_font(SANS_BOLD, 26), fill="black")
    d.text((W - 560, 100), f"Printed: {date.fromisoformat(gt['date_of_service']).strftime(date_fmt)} "
                           f"{rng.randint(8, 20):02d}:{rng.randint(0, 59):02d}", font=_font(SANS, 20), fill="black")
    rule = "-" * 72
    rows = [
        (rule, None),
        (f"Carrier: {gt['carrier']}", f"Group #: {gt['group_number']}"),
        (f"Patient: {pl.upper()}, {pf}", f"Cert/ID #: {gt['certificate_id']}"),
        (f"Rx #: {gt['rx_number']}", f"Date of Service: {date.fromisoformat(gt['date_of_service']).strftime(date_fmt)}"),
        (f"DIN: {din}", f"Drug: {name.upper()} {strength.replace(' ', '').upper()} {'TAB' if drug['form'] == 'tablet' else 'CAP'}"),
        (f"Qty: {qty}", f"Days Supply: {gt['days_supply']}"),
        (rule, None),
        (f"{'':22}{'SUBMITTED':>12}{'ADJUDICATED':>14}", None),
        (f"{'Drug Cost':22}{cost:>12.2f}{cost:>14.2f}", None),
        (f"{'Professional Fee':22}{ref.DISPENSING_FEE:>12.2f}{ref.DISPENSING_FEE:>14.2f}", None),
        (f"{'Total':22}{total:>12.2f}{total:>14.2f}", None),
        (f"{'Plan Pays':22}{'':12}{gt['amount_paid']:>14}", None),
        (f"{'Patient Pays':22}{'':12}{gt['patient_pays']:>14}", None),
        (rule, None),
    ]
    y = 170
    for left, right in rows:
        d.text((70, y), left, font=mono, fill="black")
        if right:
            d.text((640, y), right, font=mono, fill="black")
        y += 40
    d.text((70, y), f"Status: {gt['status']}", font=mono_b, fill="black")
    d.text((640, y), f"Trace #: {gt['trace_number']}", font=mono, fill="black")
    y += 40
    d.text((70, y), "Response Codes:" + ("" if codes else " (none)"), font=mono, fill="black")
    for c in codes:
        y += 36
        d.text((110, y), f"{c}  {ref.RESPONSE_CODES[c]}", font=mono, fill="black")
    d.text((70, H - 90), "Retain with prescription hard copy. Adjudicated amounts are subject to audit.",
           font=_font(SANS, 18), fill=(90, 90, 90))
    return img, gt, {"style": "claim", "date_format": date_fmt, "clinic": gt["carrier"]}


def fax_header(img, rng, sender):
    """Transmission line a fax machine prints across the top of every received page."""
    d = ImageDraw.Draw(img)
    when = datetime.combine(_rand_date(rng, date(2026, 1, 1), date(2026, 10, 1)), time(rng.randint(8, 18), rng.randint(0, 59)))
    d.rectangle((0, 0, img.width, 34), fill="white")
    d.text((12, 6), f"{when:%b %d %Y %H:%M}  FROM: {sender[:28]}  FAX {_phone(rng)}   P.1/1",
           font=_font(MONO, 19 if img.width < 1000 else 22), fill="black")
    return img


def degrade(img: Image.Image, kind: str, rng: random.Random) -> Image.Image:
    if kind == "clean":
        return img
    if kind == "skew":
        angle = rng.uniform(2.0, 5.0) * rng.choice([-1, 1])
        return img.rotate(angle, expand=True, fillcolor="white", resample=Image.BICUBIC)
    if kind == "blur":
        return img.filter(ImageFilter.GaussianBlur(radius=1.8))  # out-of-focus phone photo
    if kind == "noise":
        speckle = Image.effect_noise(img.size, 60).point(lambda p: 0 if p < 25 else 255).convert("RGB")
        out = ImageChops.darker(img, speckle)
        buf = io.BytesIO()
        out.save(buf, "JPEG", quality=20)
        return Image.open(io.BytesIO(buf.getvalue())).convert("RGB")
    if kind == "fax":
        g = img.convert("L").resize((img.width // 2, img.height // 2), Image.BILINEAR)
        g = g.point(lambda p: 255 if p > 150 else 0)
        dr = ImageDraw.Draw(g)
        for _ in range(rng.randint(3, 6)):
            yy = rng.randint(0, g.height)
            dr.line((0, yy, g.width, yy), fill=0, width=rng.randint(1, 2))
        return g.resize(img.size, Image.NEAREST).convert("RGB")
    if kind == "low_res":
        # a 75 dpi scan of a 150 dpi page
        return img.resize((img.width // 2, img.height // 2), Image.BILINEAR).resize(img.size, Image.BILINEAR)
    raise ValueError(kind)


MAKERS = {"pad": make_prescription_pad, "emr": make_prescription_emr, "invoice": make_invoice, "claim": make_claim}
DOC_TYPE = {"pad": "prescription", "emr": "prescription", "invoice": "invoice", "claim": "claim"}


def generate(n_rx: int, n_inv: int, n_claim: int, seed: int) -> list:
    """n_rx prescriptions split evenly between pad and EMR styles, plus invoices and claim responses."""
    rng = random.Random(seed)
    for p in (DOCS_DIR, GT_DIR):
        p.mkdir(parents=True, exist_ok=True)
        for f in p.glob("*"):
            f.unlink()
    jobs = [("pad", "rx")] * (n_rx - n_rx // 2) + [("emr", "rx")] * (n_rx // 2) + [("invoice", "inv")] * n_inv + [("claim", "claim")] * n_claim
    counters, manifest = {}, []
    for style, prefix in jobs:
        counters[style] = counters.get(style, 0) + 1
        i = counters[style]
        doc_id = f"{prefix}_{style}_{i:03d}" if prefix == "rx" else f"{prefix}_{i:03d}"
        img, gt, meta = MAKERS[style](rng)
        degradation = DEGRADATIONS[(i - 1) % len(DEGRADATIONS)]
        if degradation == "fax" and style != "claim":  # claim printouts come from the pharmacy's own printer
            img = fax_header(img, rng, meta["clinic"])
        degrade(img, degradation, rng).save(DOCS_DIR / f"{doc_id}.png", optimize=True)
        record = {"doc_id": doc_id, "doc_type": DOC_TYPE[style],
                  "style": style, "degradation": degradation, "date_format": meta["date_format"]}
        (GT_DIR / f"{doc_id}.json").write_text(json.dumps({**record, "fields": gt}, indent=2))
        manifest.append(record)
    (DATA_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def load_dataset() -> list:
    out = []
    for p in sorted(GT_DIR.glob("*.json")):
        rec = json.loads(p.read_text())
        rec["image_path"] = str(DOCS_DIR / f"{rec['doc_id']}.png")
        out.append(rec)
    return out
