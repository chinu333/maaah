"""Evaluator Agent -- AI-powered quality assessment using azure-ai-evaluation.

Runs four quality evaluators from the ``azure-ai-evaluation`` SDK against
every agent response and returns a structured scorecard:

1. **Relevance**    -- Is the response relevant to the question?   (1-5)
2. **Coherence**    -- Is it logically coherent and well-structured? (1-5)
3. **Fluency**      -- Is the language natural and grammatically correct? (1-5)
4. **Groundedness** -- Are claims substantiated by the context?    (1-5)

The evaluator runs **inline** (post-processing every response) and can also
be invoked **on-demand** by the user ("evaluate that", "score the last answer").

Authentication uses **DefaultAzureCredential** (role-based access).
"""

from __future__ import annotations

import asyncio
import logging
from functools import lru_cache
from typing import Any, Optional

from azure.identity import DefaultAzureCredential
from azure.ai.evaluation import (
    AzureOpenAIModelConfiguration,
    CoherenceEvaluator,
    FluencyEvaluator,
    GroundednessEvaluator,
    RelevanceEvaluator,
)

from app.config import get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Azure credential singleton
# ---------------------------------------------------------------------------
_credential = DefaultAzureCredential()


# ---------------------------------------------------------------------------
# Cached model config & evaluators (created once, reused)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _get_model_config() -> dict:
    """Return the AzureOpenAIModelConfiguration dict (cached)."""
    settings = get_settings()
    return {
        "azure_endpoint": settings.azure_openai_endpoint,
        "azure_deployment": settings.azure_openai_chat_deployment,
        "api_version": settings.azure_openai_api_version,
    }


@lru_cache(maxsize=1)
def _get_evaluators() -> dict[str, Any]:
    """Create and cache evaluator instances."""
    cfg = _get_model_config()
    return {
        "relevance": RelevanceEvaluator(model_config=cfg, credential=_credential),
        "coherence": CoherenceEvaluator(model_config=cfg, credential=_credential),
        "fluency": FluencyEvaluator(model_config=cfg, credential=_credential),
        "groundedness": GroundednessEvaluator(model_config=cfg, credential=_credential),
    }


# ---------------------------------------------------------------------------
# Core evaluation logic
# ---------------------------------------------------------------------------

def _run_single_evaluator(
    name: str,
    evaluator: Any,
    query: str,
    response: str,
    context: str | None = None,
) -> dict[str, Any]:
    """Run one evaluator synchronously and return its result dict."""
    try:
        kwargs: dict[str, str] = {"response": response}

        # Relevance & Coherence need query; Fluency does not
        if name in ("relevance", "coherence", "groundedness"):
            kwargs["query"] = query

        # Groundedness needs context
        if name == "groundedness" and context:
            kwargs["context"] = context

        result = evaluator(**kwargs)

        score = result.get(name, result.get(f"gpt_{name}"))
        passed = result.get(f"{name}_result", "unknown")
        reason = result.get(f"{name}_reason", "")

        return {
            "metric": name,
            "score": float(score) if score is not None else None,
            "result": str(passed),
            "reason": reason,
        }
    except Exception as exc:
        logger.warning("Evaluator '%s' failed: %s", name, exc)
        return {
            "metric": name,
            "score": None,
            "result": "error",
            "reason": str(exc),
        }


async def evaluate_response(
    query: str,
    response: str,
    context: str | None = None,
) -> dict[str, Any]:
    """Run all evaluators against a query/response pair.

    Returns a structured scorecard dict suitable for JSON serialisation
    and frontend rendering.
    """
    evaluators = _get_evaluators()
    loop = asyncio.get_event_loop()

    # Run evaluators in parallel using threads (they are synchronous + IO-bound)
    tasks = [
        loop.run_in_executor(
            None,
            _run_single_evaluator,
            name,
            ev,
            query,
            response,
            context,
        )
        for name, ev in evaluators.items()
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    scores: list[dict[str, Any]] = []
    for r in results:
        if isinstance(r, Exception):
            logger.error("Evaluator task exception: %s", r)
            scores.append({"metric": "unknown", "score": None, "result": "error", "reason": str(r)})
        else:
            scores.append(r)

    # Compute overall average (skip None scores)
    valid_scores = [s["score"] for s in scores if s["score"] is not None]
    overall = round(sum(valid_scores) / len(valid_scores), 1) if valid_scores else None

    # Determine overall pass/fail
    all_passed = all(s["result"] == "pass" for s in scores if s["score"] is not None)

    scorecard = {
        "scores": scores,
        "overall_score": overall,
        "overall_max": 5,
        "overall_result": "pass" if all_passed else "needs_review",
    }

    logger.info(
        "Evaluation complete: overall=%.1f/5 (%s) | %s",
        overall or 0,
        scorecard["overall_result"],
        " | ".join(f"{s['metric']}={s['score']}" for s in scores),
    )

    return scorecard


# ---------------------------------------------------------------------------
# On-demand agent interface  (user says "evaluate that")
# ---------------------------------------------------------------------------

async def invoke(
    query: str,
    *,
    file_path: Optional[str] = None,
    history: str = "",
    **kwargs,
) -> str:
    """On-demand evaluation: find the last assistant response in history and score it."""
    # Extract the last Q&A pair from history
    last_query = ""
    last_response = ""

    if history:
        lines = history.strip().split("\n")
        for line in reversed(lines):
            if line.startswith("Assistant:") and not last_response:
                last_response = line[len("Assistant:"):].strip()
            elif line.startswith("User:") and not last_query:
                last_query = line[len("User:"):].strip()
            if last_query and last_response:
                break

    if not last_response:
        return (
            "I don't have a previous response to evaluate. "
            "Please ask a question first, then ask me to evaluate the response."
        )

    scorecard = await evaluate_response(
        query=last_query or query,
        response=last_response,
    )

    # Format as Markdown
    return _format_scorecard_markdown(scorecard, last_query, last_response)


def _format_scorecard_markdown(
    scorecard: dict[str, Any],
    query: str = "",
    response: str = "",
) -> str:
    """Render the scorecard as a readable Markdown block."""
    lines = ["## Quality Evaluation Scorecard\n"]

    if query:
        q_preview = query[:120] + "..." if len(query) > 120 else query
        lines.append(f"**Evaluated query:** {q_preview}\n")

    lines.append("| Metric | Score | Result | Reasoning |")
    lines.append("|--------|-------|--------|-----------|")

    emoji_map = {"pass": "Pass", "fail": "Fail", "needs_review": "Review", "error": "Error", "unknown": "N/A"}

    for s in scorecard["scores"]:
        score_str = f"{s['score']:.1f}/5" if s["score"] is not None else "N/A"
        result_str = emoji_map.get(s["result"], s["result"])
        reason = s.get("reason", "")[:150]
        lines.append(f"| **{s['metric'].title()}** | {score_str} | {result_str} | {reason} |")

    overall = scorecard.get("overall_score")
    overall_str = f"{overall:.1f}/5" if overall is not None else "N/A"
    overall_result = emoji_map.get(scorecard.get("overall_result", ""), "")
    lines.append(f"\n**Overall: {overall_str}** ({overall_result})")

    return "\n".join(lines)
