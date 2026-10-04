"""Per-call LLM token/cost consumption metrics (AGT-030).

`llm_metrics.py` tracks *duration*; this tracks *how much it cost* -- the project owner wanted to
compare `agentic-ai`'s OpenRouter spend against `enterprise-rag-platform`'s own, and nothing
previously captured per-call token counts or cost at all (only Langfuse's point-in-time trace
events, which don't aggregate).

Token counts come from PydanticAI's `RunUsage` (`result.usage()`), which is model-agnostic and
always populated. Cost is computed from a small, explicit per-model price table below rather than
trusted from the provider response, since not every PydanticAI model backend surfaces OpenRouter's
proprietary `usage.cost` field -- an unlisted model records tokens but no cost, visibly (as
`"unknown"`), rather than silently reporting $0.
"""

from typing import Any

from opentelemetry.metrics import Counter

from app.core.telemetry import get_meter

# USD per token, not per million -- matches OpenRouter's own live pricing (checked 2026-10-04 via
# GET https://openrouter.ai/api/v1/models). Update here whenever the configured model changes;
# the metric is labeled by model name specifically so historical data stays correctly priced even
# if this table drifts later.
_PRICE_PER_TOKEN_USD: dict[str, tuple[float, float]] = {
    # model: (input_price, output_price)
    "google/gemma-3-27b-it": (0.00000008, 0.00000045),
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free": (0.0, 0.0),
    "nvidia/nemotron-3.5-lightning:free": (0.0, 0.0),
}

_tokens_counter: Counter | None = None
_cost_counter: Counter | None = None


def _get_tokens_counter() -> Counter:
    global _tokens_counter
    if _tokens_counter is None:
        _tokens_counter = get_meter().create_counter(
            name="agentic_ai_llm_tokens_total",
            description="Input/output tokens consumed per LLM call, by agent/model/token type",
        )
    return _tokens_counter


def _get_cost_counter() -> Counter:
    global _cost_counter
    if _cost_counter is None:
        # No `unit=` kwarg: the OTel-to-Prometheus bridge appends the unit to the metric name
        # (found live -- `unit="USD"` turned this into `agentic_ai_llm_cost_usd_USD_total`,
        # silently un-queryable under the name anyone would actually guess). The metric name
        # already says "usd" in plain text, so the unit field would only ever be redundant here.
        _cost_counter = get_meter().create_counter(
            name="agentic_ai_llm_cost_usd_total",
            description="Estimated USD cost of LLM calls, by agent/model (unpriced models record 0)",
        )
    return _cost_counter


def _resolve_model_name(result: Any) -> str:
    """The model that actually produced the final response -- not necessarily the configured
    primary, since `FallbackModel` may have used the fallback instead. `AgentRunResult.response`
    raises `ValueError` if no response exists at all (not expected for a completed run, but
    guarded rather than assumed).
    """
    try:
        return result.response.model_name or "unknown"
    except ValueError:
        return "unknown"


def record_llm_usage(agent_name: str, result: Any) -> None:
    """Record token counts and estimated USD cost for one completed PydanticAI `agent.run()`
    call, reading real usage off its result rather than estimating.
    """
    usage = result.usage
    model_name = _resolve_model_name(result)

    tokens = _get_tokens_counter()
    tokens.add(usage.input_tokens, attributes={"agent": agent_name, "model": model_name, "token_type": "input"})
    tokens.add(usage.output_tokens, attributes={"agent": agent_name, "model": model_name, "token_type": "output"})

    input_price, output_price = _PRICE_PER_TOKEN_USD.get(model_name, (0.0, 0.0))
    cost = usage.input_tokens * input_price + usage.output_tokens * output_price
    _get_cost_counter().add(cost, attributes={"agent": agent_name, "model": model_name})
