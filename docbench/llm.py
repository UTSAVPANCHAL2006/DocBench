"""Claude-based extraction: from the page image (vision) or from OCR text only."""
import base64
import json
import time

import anthropic

from .config import PRICING

# Models that accept the server-side refusal fallback ("default" form) on the Claude API.
_FALLBACK_MODELS = {"claude-opus-5-5", "claude-sonnet-5-5"}

SYSTEM = """You extract fields from Canadian pharmacy documents (prescriptions, wholesaler invoices, claim adjudication responses) for a data pipeline.
Rules:
- Copy values exactly as written. Do not correct spelling, expand abbreviations, or guess.
- If a field is not on the document or is unreadable, return an empty string. Never invent a value.
- Dates: return YYYY-MM-DD. A numeric date written NN/NN/YYYY is day/month/year (Canadian convention).
- Prescriptions: one entry in "medications" per drug prescribed. drug_name is the drug name only;
  strength is number + unit (e.g. "0.5 mg"); sig is the directions exactly as written;
  quantity and refills are plain integers ("No refills" -> "0", "Dispense: 60 (sixty)" -> "60").
- Invoices: one entry in "line_items" per product row, including backordered rows. din is empty for items
  without one. taxable is "T" if the row is marked taxable, else empty.
- Claim responses: status is PAID or REJECTED as printed; total_submitted is the submitted Total;
  amount_paid is the "Plan Pays" amount (what the insurer pays, not the total); patient_pays is "Patient Pays";
  response_codes is a comma-separated list of the 2-character codes only (e.g. "D7,LO"), empty if none.
- prescriber_license is the registration number digits only.
- Money and quantities: plain numbers, no "$" or thousands separators."""

# From OCR text, "copy exactly" would copy OCR's mistakes too; repairing obvious character
# confusions is the point of this pipeline, guessing unreadable values is not.
OCR_PROMPT = """Extract the {doc_type} fields from this OCR text of a scanned page.
The OCR may contain character errors (e.g. "|" or "l" for 1, "O" for 0, broken words). Fix such obvious
recognition errors, but if a value is genuinely unreadable return an empty string rather than guessing.

{ocr_text}"""

_STR = {"type": "string"}


def _obj(props, extra=None):
    properties = {p: _STR for p in props}
    properties.update(extra or {})
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


RX_SCHEMA = _obj(["patient_name", "patient_dob", "health_card", "date_written", "prescriber_name", "prescriber_license"],
                 {"medications": {"type": "array", "items": _obj(["drug_name", "strength", "sig", "quantity", "refills"])}})
INV_SCHEMA = _obj(["supplier", "invoice_number", "invoice_date", "account_number", "po_number", "subtotal", "hst", "total"],
                  {"line_items": {"type": "array", "items": _obj(["din", "description", "qty_ordered", "qty_shipped",
                                                                  "unit_cost", "line_total", "taxable"])}})
CLAIM_SCHEMA = _obj(["carrier", "group_number", "patient_name", "certificate_id", "rx_number", "date_of_service", "din",
                     "drug_name", "strength", "quantity", "days_supply", "total_submitted", "amount_paid", "patient_pays",
                     "status", "response_codes", "trace_number"])
SCHEMAS = {"prescription": RX_SCHEMA, "invoice": INV_SCHEMA, "claim": CLAIM_SCHEMA}


class ClaudeExtractor:
    def __init__(self, model: str, effort: str):
        self.model, self.effort = model, effort
        self.client = anthropic.Anthropic()

    def extract(self, doc_type: str, image_path: str = None, ocr_text: str = None):
        """Returns (fields, latency_ms, cost_usd, usage)."""
        if image_path:
            data = base64.standard_b64encode(open(image_path, "rb").read()).decode()
            content = [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": data}},
                       {"type": "text", "text": f"Extract the {doc_type} fields from this image."}]
        else:
            content = OCR_PROMPT.format(doc_type=doc_type, ocr_text=ocr_text)

        kwargs = dict(
            model=self.model,
            max_tokens=8000,
            system=SYSTEM,
            messages=[{"role": "user", "content": content}],
            output_config={"effort": self.effort,
                           "format": {"type": "json_schema",
                                      "schema": SCHEMAS[doc_type]}},
        )
        if self.model in _FALLBACK_MODELS:
            kwargs.update(betas=["server-side-fallback-2026-07-01"], fallbacks="default")

        start = time.perf_counter()
        response = self.client.beta.messages.create(**kwargs)
        latency_ms = (time.perf_counter() - start) * 1000

        if response.stop_reason == "refusal":
            raise RuntimeError(f"refused: {getattr(response.stop_details, 'category', None)}")
        text = next(b.text for b in response.content if b.type == "text")
        usage = {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens}
        price = PRICING.get(response.model, PRICING.get(self.model))
        cost = (usage["input_tokens"] * price["input"] + usage["output_tokens"] * price["output"]) / 1e6
        return json.loads(text), latency_ms, cost, usage


class OpenAIExtractor:
    """Same prompt, schema and return shape as ClaudeExtractor, via OpenAI Chat Completions
    with strict JSON-schema structured outputs."""

    def __init__(self, model: str, effort: str):
        import openai  # optional dependency: only needed when an OpenAI model is benchmarked
        self.model = model
        # GPT-5 / o-series reasoning effort accepts low|medium|high; clamp the higher Claude levels.
        self.effort = {"xhigh": "high", "max": "high"}.get(effort, effort)
        self.client = openai.OpenAI()

    def extract(self, doc_type: str, image_path: str = None, ocr_text: str = None):
        """Returns (fields, latency_ms, cost_usd, usage)."""
        if image_path:
            data = base64.standard_b64encode(open(image_path, "rb").read()).decode()
            content = [{"type": "image_url", "image_url": {"url": f"data:image/png;base64,{data}", "detail": "high"}},
                       {"type": "text", "text": f"Extract the {doc_type} fields from this image."}]
        else:
            content = OCR_PROMPT.format(doc_type=doc_type, ocr_text=ocr_text)
        kwargs = dict(
            model=self.model,
            max_completion_tokens=8000,
            messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": content}],
            response_format={"type": "json_schema",
                             "json_schema": {"name": f"{doc_type}_fields", "schema": SCHEMAS[doc_type], "strict": True}},
        )
        if self.model.startswith(("gpt-5", "o3", "o4")):
            kwargs["reasoning_effort"] = self.effort

        start = time.perf_counter()
        response = self.client.chat.completions.create(**kwargs)
        latency_ms = (time.perf_counter() - start) * 1000

        choice = response.choices[0]
        if choice.message.refusal:
            raise RuntimeError(f"refused: {choice.message.refusal}")
        if choice.finish_reason == "length":
            raise RuntimeError("output truncated at max_completion_tokens")
        usage = {"input_tokens": response.usage.prompt_tokens, "output_tokens": response.usage.completion_tokens}
        price = PRICING.get(self.model)
        cost = (usage["input_tokens"] * price["input"] + usage["output_tokens"] * price["output"]) / 1e6
        return json.loads(choice.message.content), latency_ms, cost, usage


def make_extractor(model: str, effort: str):
    if model not in PRICING:
        raise ValueError(f"No price for {model!r} in docbench/config.py PRICING - add it so cost is measured, not guessed.")
    return ClaudeExtractor(model, effort) if model.startswith("claude") else OpenAIExtractor(model, effort)
