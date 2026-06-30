"""Per-model pricing for budget enforcement + metering (Phase 2).

Cost = prompt_tokens/1k * input + completion_tokens/1k * output (USD).

Rates below are current published list prices for the configured models as of
LAST_VERIFIED — NOT a contract. Confirm against the provider's pricing page before
relying on a figure on an invoice (same "verify against the version you deploy"
discipline as litellm-config.yaml). Override any rate at runtime via
GATEWAY_PRICING (JSON: {"model": [in_per_1k, out_per_1k]}).

A model with NO rate (table miss) is NOT free: it is priced at the conservative
FALLBACK (so spend is over- not under-counted at a budget ceiling) and every such
charge is flagged `estimated=True` so the metering/billing layer can mark it as
non-authoritative rather than silently book a wrong number.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Dict, Tuple

_log = logging.getLogger("gateway.pricing")

# Published list prices last reviewed on this date; re-verify before invoicing.
LAST_VERIFIED = "2026-06-30"

# (input_per_1k, output_per_1k) USD. gov/* are served from a different boundary
# (AWS GovCloud Bedrock) and may price differently — verify before gov invoicing.
_DEFAULT: Dict[str, Tuple[float, float]] = {
    # OpenAI (commercial)
    "gpt-4o": (0.0025, 0.010),
    "gpt-4o-mini": (0.00015, 0.0006),
    # Anthropic (commercial)
    "claude-fable-5": (0.015, 0.075),
    "claude-opus-4-8": (0.015, 0.075),
    "claude-sonnet-4-6": (0.003, 0.015),
    "claude-haiku-4-5": (0.0008, 0.004),
    # Google (commercial)
    "gemini-2.5-pro": (0.00125, 0.010),
    "gemini-2.5-flash": (0.0003, 0.0025),
    # gov/* — AWS GovCloud (Bedrock). gpt-oss are open-weight (cheap serverless);
    # proprietary + Claude mirror their commercial list until gov rates are confirmed.
    "gov/claude-opus-4-8": (0.015, 0.075),
    "gov/gpt-5.5": (0.00125, 0.010),
    "gov/gpt-oss-120b": (0.00015, 0.0006),
    "gov/gpt-oss-20b": (0.00007, 0.0003),
}

# Conservative default for an unknown model — opus-level, so a missing rate
# over-counts (safe at a ceiling) rather than under-counts. Override via env.
_DEFAULT_FALLBACK: Tuple[float, float] = (0.015, 0.075)


def _load_overrides() -> Dict[str, Tuple[float, float]]:
    raw = os.environ.get("GATEWAY_PRICING")
    if not raw:
        return {}
    try:
        return {k: (float(v[0]), float(v[1])) for k, v in json.loads(raw).items()}
    except Exception:  # noqa: BLE001
        _log.warning("GATEWAY_PRICING is not valid JSON; ignoring overrides")
        return {}


def _load_fallback() -> Tuple[float, float]:
    raw = os.environ.get("GATEWAY_PRICING_FALLBACK")
    if not raw:
        return _DEFAULT_FALLBACK
    try:
        v = json.loads(raw)
        return (float(v[0]), float(v[1]))
    except Exception:  # noqa: BLE001
        _log.warning("GATEWAY_PRICING_FALLBACK is not valid JSON; using default")
        return _DEFAULT_FALLBACK


_RATES = {**_DEFAULT, **_load_overrides()}
_FALLBACK = _load_fallback()


def price(model: str, prompt_tokens: int, completion_tokens: int) -> Tuple[float, bool]:
    """Return (cost_usd, estimated). estimated=True means the model had no rate
    and the conservative fallback was applied — the cost is non-authoritative."""
    rate = _RATES.get(model)
    estimated = rate is None
    if rate is None:
        rate = _FALLBACK
        _log.warning(
            "pricing: no rate for model %r; charging fallback %s/%s per 1k "
            "(flagged estimated — set GATEWAY_PRICING to make it authoritative)",
            model, rate[0], rate[1])
    cost = round((prompt_tokens / 1000.0) * rate[0]
                 + (completion_tokens / 1000.0) * rate[1], 6)
    return cost, estimated


def cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Back-compatible cost-only helper. Unknown models use the fallback rate
    (never 0); use price() when you need the estimated flag."""
    return price(model, prompt_tokens, completion_tokens)[0]


def known(model: str) -> bool:
    return model in _RATES
