"""Reference data and the correction helpers built on it.

Drug and brand names are real (Canadian market), but every DIN here is SYNTHETIC
(random 8-digit numbers in DIN format). They are not real Health Canada DINs.
"""
import difflib
import random
import re

DRUGS = [
    {"name": "Amoxicillin", "brands": ["Amoxil"], "strengths": ["250 mg", "500 mg"], "form": "capsule"},
    {"name": "Atorvastatin", "brands": ["Lipitor"], "strengths": ["10 mg", "20 mg", "40 mg"], "form": "tablet"},
    {"name": "Metformin", "brands": ["Glucophage"], "strengths": ["500 mg", "850 mg"], "form": "tablet"},
    {"name": "Metronidazole", "brands": ["Flagyl"], "strengths": ["250 mg", "500 mg"], "form": "tablet"},
    {"name": "Hydroxyzine", "brands": ["Atarax"], "strengths": ["10 mg", "25 mg"], "form": "tablet"},
    {"name": "Hydralazine", "brands": ["Apresoline"], "strengths": ["10 mg", "25 mg"], "form": "tablet"},
    {"name": "Clonazepam", "brands": ["Rivotril"], "strengths": ["0.5 mg", "2 mg"], "form": "tablet"},
    {"name": "Clonidine", "brands": ["Catapres"], "strengths": ["0.1 mg", "0.2 mg"], "form": "tablet"},
    {"name": "Levothyroxine", "brands": ["Synthroid", "Eltroxin"], "strengths": ["50 mcg", "100 mcg", "125 mcg"], "form": "tablet"},
    {"name": "Warfarin", "brands": ["Coumadin"], "strengths": ["1 mg", "2.5 mg", "5 mg"], "form": "tablet"},
    {"name": "Lisinopril", "brands": ["Zestril", "Prinivil"], "strengths": ["5 mg", "10 mg", "20 mg"], "form": "tablet"},
    {"name": "Amlodipine", "brands": ["Norvasc"], "strengths": ["5 mg", "10 mg"], "form": "tablet"},
    {"name": "Sertraline", "brands": ["Zoloft"], "strengths": ["50 mg", "100 mg"], "form": "capsule"},
    {"name": "Citalopram", "brands": ["Celexa"], "strengths": ["10 mg", "20 mg"], "form": "tablet"},
    {"name": "Celecoxib", "brands": ["Celebrex"], "strengths": ["100 mg", "200 mg"], "form": "capsule"},
    {"name": "Prednisone", "brands": ["Winpred"], "strengths": ["5 mg", "50 mg"], "form": "tablet"},
    {"name": "Ramipril", "brands": ["Altace"], "strengths": ["2.5 mg", "5 mg", "10 mg"], "form": "capsule"},
]
DRUG_BY_NAME = {d["name"].lower(): d for d in DRUGS}
# Every way a drug is written (generic or brand) -> its generic name.
DRUG_ALIASES = {alias.lower(): d["name"] for d in DRUGS for alias in [d["name"], *d["brands"]]}

# Canadian generic products are often named "<MANUFACTURER>-<MOLECULE>" (e.g. on invoices
# and pharmacy labels); the prefix tells you who made it, not what it is.
GENERIC_PREFIXES = ["APO-", "TEVA-", "PMS-", "MYLAN-", "SANDOZ "]
_PREFIX_RE = re.compile(r"^(?:APO|TEVA|PMS|MYLAN|AURO|JAMP|MINT)-\s*|^SANDOZ\s+", re.I)

# Look-alike / sound-alike pairs deliberately included as edge cases (generic and brand).
LOOK_ALIKE = [("Hydroxyzine", "Hydralazine"), ("Clonazepam", "Clonidine"), ("Metformin", "Metronidazole"),
              ("Citalopram", "Celecoxib")]  # Celexa / Celebrex is a classic brand-name mix-up


_FORM_WORDS = {"tab", "tabs", "tablet", "tablets", "cap", "caps", "capsule", "capsules"}


def canonical_drug(name: str) -> str:
    """'Lipitor', 'APO-ATORVASTATIN', 'atorvastatin' -> 'Atorvastatin'. Exact lookups only:
    a misspelling is left alone so it still counts as an error."""
    stripped = _PREFIX_RE.sub("", name.strip())
    # "HYDRALAZINE 25MG TAB" -> "HYDRALAZINE": strength and dosage form aren't part of the name
    words = []
    for w in stripped.split():
        if re.search(r"\d|(mg|mcg)$", w, re.I) or w.lower() in _FORM_WORDS:
            break
        words.append(w)
    stripped = " ".join(words) or stripped
    return DRUG_ALIASES.get(stripped.lower(), stripped)

# Handwritten pads use Latin shorthand; EMR printouts spell directions out in plain English.
SIG_TEMPLATES = [
    "1 {u} PO daily",
    "1 {u} PO BID",
    "1 {u} PO TID x 7 days",
    "1 {u} PO QHS",
    "1-2 {u}s PO Q4-6H PRN pain",
    "1/2 {u} PO daily",
    "2 {u}s PO BID with food",
]
SIG_TEMPLATES_EMR = [
    "Take 1 {f} by mouth once daily",
    "Take 1 {f} by mouth twice daily",
    "Take 1 {f} by mouth three times daily for 7 days",
    "Take 1 {f} by mouth at bedtime",
    "Take 1 to 2 {f}s by mouth every 4 to 6 hours as needed for pain",
    "Take 1/2 {f} by mouth once daily",
    "Take 2 {f}s by mouth twice daily with food",
]
SIG_UNIT = {"tablet": "tab", "capsule": "cap"}

# Non-prescription stock on wholesaler invoices. OTC drugs carry a DIN; supplies don't.
# Unlike prescription drugs (zero-rated), these are taxable (13% HST in Ontario).
OTC_ITEMS = [
    {"description": "ACETAMINOPHEN 500MG CAPLET 100", "has_din": True},
    {"description": "IBUPROFEN 200MG TAB 100", "has_din": True},
    {"description": "CETIRIZINE 10MG TAB 30", "has_din": True},
    {"description": "LORATADINE 10MG TAB 24", "has_din": True},
    {"description": "ADHESIVE BANDAGES ASSORTED 30", "has_din": False},
    {"description": "PILL ORGANIZER 7-DAY", "has_din": False},
    {"description": "DIGITAL THERMOMETER", "has_din": False},
]
HST_RATE = 0.13

# Claim adjudication. Only response codes I could confirm from public provincial / vendor
# documentation are used; the full CPhA Pharmacy Claim Standard table is not public.
RESPONSE_CODES = {
    "D7": "Refill too soon",
    "D4": "Refills not covered",
    "LO": "Benefit maximum exceeded",
    "57": "SSC error",
}
CARRIERS = ["Maple Health Benefits", "Northern Shield Insurance", "Trillium Group Benefits"]  # fictional
DISPENSING_FEE = 12.99

SIG_EXPANSIONS = {
    "po": "by mouth", "bid": "twice daily", "tid": "three times daily", "qid": "four times daily",
    "qhs": "at bedtime", "prn": "as needed", "daily": "once daily", "q4-6h": "every 4 to 6 hours",
    "tab": "tablet", "tabs": "tablets", "cap": "capsule", "caps": "capsules", "x": "for",
}
SIG_VOCAB = sorted({"PO", "BID", "TID", "QID", "QHS", "PRN", "Q4-6H", "daily", "tab", "tabs",
                    "cap", "caps", "x", "days", "pain", "with", "food",
                    "Take", "tablet", "tablets", "capsule", "capsules", "by", "mouth", "once", "twice",
                    "three", "times", "at", "bedtime", "every", "to", "hours", "as", "needed", "for"})


def _make_catalogue():
    rng = random.Random(2024)
    rows = []
    for d in DRUGS:
        for s in d["strengths"]:
            din = "0" + "".join(rng.choice("0123456789") for _ in range(7))
            rows.append({"din": din, "drug": d["name"], "strength": s, "form": d["form"],
                         "pack": rng.choice([30, 100, 500])})
    return rows


def _make_otc_dins():
    rng = random.Random(2025)
    return {it["description"]: "0" + "".join(rng.choice("0123456789") for _ in range(7))
            for it in OTC_ITEMS if it["has_din"]}


CATALOGUE = _make_catalogue()
OTC_DINS = _make_otc_dins()
DIN_SET = {r["din"] for r in CATALOGUE} | set(OTC_DINS.values())

_DIGIT_FIXES = str.maketrans({"O": "0", "o": "0", "D": "0", "Q": "0", "l": "1", "I": "1",
                              "|": "1", "!": "1", "i": "1", "S": "5", "s": "5", "B": "8", "Z": "2"})


def fix_digits(token: str) -> str:
    """Undo common OCR letter-for-digit swaps (O->0, l->1, S->5...)."""
    return token.translate(_DIGIT_FIXES)


def expand_sig(sig: str) -> str:
    """'1 tab PO BID' -> '1 tablet by mouth twice daily'."""
    return " ".join(SIG_EXPANSIONS.get(t.lower(), t) for t in sig.split())


def match_drug(text: str, min_score: float = 0.8, min_margin: float = 0.1):
    """Snap an OCR'd drug name (generic, brand or manufacturer-prefixed) to its generic.

    Returns (name, needs_review). Only corrects when the best match is both close
    and clearly better than the runner-up, so a garbled 'Hydr...zine' is flagged
    rather than silently turned into the wrong look-alike drug.
    """
    text = _PREFIX_RE.sub("", text.strip())
    if not text:
        return text, True
    # Score every alias (generic and brand), keep the best score per generic, then
    # compare the top two *different* drugs - Lipitor vs Atorvastatin is no ambiguity.
    best_per_drug = {}
    for alias, generic in DRUG_ALIASES.items():
        s = difflib.SequenceMatcher(None, text.lower(), alias).ratio()
        best_per_drug[generic] = max(s, best_per_drug.get(generic, 0.0))
    scored = sorted(((s, g) for g, s in best_per_drug.items()), reverse=True)
    (best, name), (second, _) = scored[0], scored[1]
    if best == 1.0:
        return name, False
    if best >= min_score and best - second >= min_margin:
        return name, False
    return text, True


def normalize_strength(text: str) -> str:
    m = re.match(r"\s*([0-9OolISsBZ!.,]+)\s*(mg|mcg|meg|g|ml)\b", text, re.I)
    if not m:
        return text.strip()
    num = fix_digits(m.group(1)).replace(",", ".")
    unit = m.group(2).lower().replace("meg", "mcg")
    return f"{num} {unit}"


def strength_is_known(drug: str, strength: str) -> bool:
    d = DRUG_BY_NAME.get(drug.lower())
    return bool(d) and strength in d["strengths"]


def sig_is_plausible(sig: str) -> bool:
    """Every word of the directions is a dose number or a known sig word. Catches misreads
    like "Q4H5" for QHS or "fab" for tab; can't catch a valid-looking swap like "12" for "1-2"."""
    sig = re.sub(r"^\s*(sig|directions)\s*[:;.]?\s*", "", sig, flags=re.I)
    vocab = {v.lower() for v in SIG_VOCAB}
    words = [w.strip(",.;:") for w in sig.split()]
    return bool(words) and all(re.fullmatch(r"[\d/\-.]+", w) or w.lower() in vocab for w in words if w)


def correct_sig(sig: str) -> str:
    """Fix OCR typos in sig tokens against the known abbreviation vocabulary."""
    lower_vocab = {v.lower(): v for v in SIG_VOCAB}
    out = []
    for i, tok in enumerate(sig.split()):
        if i == 0 and tok in {"I", "l", "|", "{", "i"}:  # leading dose count misread as a letter
            out.append("1")
            continue
        tok = re.sub(r"^([\d/\-]+)[.,:]$", r"\1", tok)  # stray OCR punctuation: "1-2." -> "1-2"
        if re.fullmatch(r"[\d/\-.]+", tok) or tok.lower() in lower_vocab:
            out.append(tok)
            continue
        as_letters = tok.lower().translate(str.maketrans("0158", "oisb"))  # P0 -> po, Q1D -> qid
        close = difflib.get_close_matches(as_letters, lower_vocab, n=1, cutoff=0.6)
        if close and re.search(r"[a-zA-Z]", tok):
            out.append(lower_vocab[close[0]])
        elif re.search(r"\d", tok):
            out.append(fix_digits(tok))
        else:
            out.append(tok)
    return " ".join(out)


def repair_din(text: str):
    """Returns (din, needs_review). Exact catalogue hit = trusted; a unique
    1-digit-off match is corrected but flagged; anything else is flagged as-is."""
    din = re.sub(r"\s", "", fix_digits(text))
    if din in DIN_SET:
        return din, False
    near = [d for d in DIN_SET if len(d) == len(din) and sum(a != b for a, b in zip(d, din)) == 1]
    if len(near) == 1:
        return near[0], True
    return din, True
