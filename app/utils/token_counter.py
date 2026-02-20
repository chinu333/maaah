"""Request-scoped token counter.

Usage in workflow:
    from app.utils.token_counter import add_tokens, get_totals, reset_counter

    reset_counter()
    ... run agents (including asyncio.gather) ...
    totals = get_totals()   # {"input_tokens": ..., "output_tokens": ..., "total_tokens": ..., "cost": ...}

Each agent calls `add_tokens(response)` after `llm.ainvoke()` where
`response` is an AIMessage with `usage_metadata`.

NOTE: We use a *mutable dict* so that child asyncio tasks (which inherit
a shallow copy of the parent context) still write to the **same** object.
ContextVar.set() would create a new value only visible in the child task.
"""

from __future__ import annotations

import threading
from typing import Any

# GPT-4.1 pricing (Azure OpenAI, as of 2025-Q4)
_COST_PER_1K_INPUT = 0.002    # $2.00 per 1M input tokens
_COST_PER_1K_OUTPUT = 0.008   # $8.00 per 1M output tokens

# Mutable shared accumulator — reset per request
_accumulator: dict[str, int] = {"input": 0, "output": 0}
_lock = threading.Lock()


def reset_counter() -> None:
    """Reset token counts for the current request."""
    with _lock:
        _accumulator["input"] = 0
        _accumulator["output"] = 0


def add_tokens(response: Any) -> None:
    """Extract usage_metadata from an AIMessage and accumulate tokens.

    Safe to call from multiple concurrent agents — uses a lock.
    Also handles cases where usage_metadata is missing gracefully.
    """
    meta = getattr(response, "usage_metadata", None)
    if not meta:
        # Try response_metadata.token_usage (older LangChain format)
        resp_meta = getattr(response, "response_metadata", {})
        token_usage = resp_meta.get("token_usage", {})
        if token_usage:
            meta = {
                "input_tokens": token_usage.get("prompt_tokens", 0),
                "output_tokens": token_usage.get("completion_tokens", 0),
            }
    if not meta:
        return

    inp = meta.get("input_tokens", 0) or 0
    out = meta.get("output_tokens", 0) or 0

    with _lock:
        _accumulator["input"] += inp
        _accumulator["output"] += out


def get_totals() -> dict[str, Any]:
    """Return accumulated token counts and estimated cost."""
    with _lock:
        inp = _accumulator["input"]
        out = _accumulator["output"]
    total = inp + out
    cost = (inp / 1000) * _COST_PER_1K_INPUT + (out / 1000) * _COST_PER_1K_OUTPUT
    return {
        "input_tokens": inp,
        "output_tokens": out,
        "total_tokens": total,
        "estimated_cost": round(cost, 6),
    }
