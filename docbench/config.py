from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DOCS_DIR = DATA_DIR / "docs"
GT_DIR = DATA_DIR / "ground_truth"
RESULTS_DIR = ROOT / "results"

DEFAULT_MODEL = "claude-opus-5-5"

# USD per 1M tokens (Anthropic first-party list prices, checked 2026-10).
# Thinking tokens are billed as output tokens and are included in usage.output_tokens.
PRICING = {
    "claude-opus-5-5": {"input": 4.00, "output": 20.00},
    "claude-sonnet-5-5": {"input": 2.00, "output": 10.00},
    "claude-haiku-5-5": {"input": 0.10, "output": 0.50},
    # OpenAI standard (non-batch) prices from developers.openai.com/api/docs/pricing, checked 2026-10.
    # Reasoning tokens are billed as output and are included in usage.completion_tokens.
    "gpt-5.5": {"input": 5.00, "output": 30.00},
    "gpt-5.4": {"input": 2.50, "output": 15.00},
    "gpt-5.4-mini": {"input": 0.75, "output": 4.50},
    "gpt-5.4-nano": {"input": 0.20, "output": 1.25},
    "gpt-5-mini": {"input": 0.25, "output": 2.00},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
}

DEGRADATIONS = ["clean", "skew", "blur", "noise", "fax", "low_res"]
