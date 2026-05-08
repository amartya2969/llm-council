"""
Three-stage council orchestration:
  Stage 1 — each active model answers the query independently
  Stage 2 — each model peer-reviews all other models' answers (anonymized)
  Stage 3 — Claude Opus (Chairman) synthesizes a final answer
"""

from __future__ import annotations
import asyncio
import string
from dataclasses import dataclass, field
from typing import Optional

import providers


# ─── Prompts ──────────────────────────────────────────────────────────────────

STAGE1_SYSTEM = """You are a member of an expert council.
Answer the user's question or evaluate their strategy thoroughly and honestly.
Be concise but comprehensive. Do not hedge excessively."""


STAGE2_SYSTEM = """You are a critical peer reviewer on an expert council.
You will be shown multiple responses to the same query, labelled Model A, Model B, etc.
Your identity and the identity of the other models are hidden to ensure unbiased evaluation."""

# ── THIS IS YOUR CONTRIBUTION ──────────────────────────────────────────────────
# The peer review prompt shapes the entire quality of Stage 2.
# The {responses_block} placeholder will be filled with all Stage 1 answers.
# Your prompt should instruct the model on HOW to critique — consider:
#   - Should it rank the responses? Surface disagreements? Find logical flaws?
#   - Should it be adversarial or collegial?
#   - What output format makes the Chairman's job (Stage 3) easiest?
#
# Replace the placeholder below with your peer review prompt.
# Keep {responses_block} in the string — it gets filled at runtime.

STAGE2_USER_TEMPLATE = """{responses_block}

Review each response above critically. For each one:
1. Identify its strongest point
2. Identify its biggest weakness or blind spot
3. Rate it 1-5 for overall quality and reasoning

Finally, note any key insight that appeared in only one response and is worth preserving.
Be direct and specific."""
# ── END OF YOUR CONTRIBUTION SECTION ──────────────────────────────────────────


STAGE3_SYSTEM = """You are Claude Opus, the Chairman of an expert council.
You have received the original query, all council members' initial responses,
and each member's peer review of the others.
Your job is to synthesize this into a single, definitive, well-reasoned final answer.
Acknowledge genuine disagreements rather than papering over them."""

STAGE3_USER_TEMPLATE = """## Original Query
{query}

## Council Responses (Stage 1)
{responses_block}

## Peer Reviews (Stage 2)
{reviews_block}

Synthesize all of the above into a final answer. Where council members disagreed,
explain the tension and take a position. Surface the single most important insight."""


# ─── Data structures ──────────────────────────────────────────────────────────

@dataclass
class ModelResponse:
    model_key: str
    display_name: str
    response: str
    error: Optional[str] = None


@dataclass
class CouncilResult:
    query: str
    stage1: list[ModelResponse] = field(default_factory=list)
    stage2: list[ModelResponse] = field(default_factory=list)
    chairman_synthesis: str = ""
    error: Optional[str] = None


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _build_responses_block(responses: list[ModelResponse]) -> str:
    """Format Stage 1 responses with anonymous labels (Model A, B, C…)."""
    labels = list(string.ascii_uppercase)
    lines = []
    for i, r in enumerate(responses):
        label = labels[i] if i < len(labels) else f"Model {i+1}"
        if r.error:
            lines.append(f"### Model {label}\n[Error: {r.error}]")
        else:
            lines.append(f"### Model {label}\n{r.response}")
    return "\n\n".join(lines)


def _build_reviews_block(reviews: list[ModelResponse]) -> str:
    labels = list(string.ascii_uppercase)
    lines = []
    for i, r in enumerate(reviews):
        label = labels[i] if i < len(labels) else f"Model {i+1}"
        if r.error:
            lines.append(f"### Review by Model {label}\n[Error: {r.error}]")
        else:
            lines.append(f"### Review by Model {label}\n{r.response}")
    return "\n\n".join(lines)


# ─── Orchestration ────────────────────────────────────────────────────────────

async def _run_stage1(query: str, active_models: list[str]) -> list[ModelResponse]:
    async def _call(model_key: str) -> ModelResponse:
        meta = providers.MODELS[model_key]
        try:
            text = await providers.complete(model_key, STAGE1_SYSTEM, query)
            return ModelResponse(model_key=model_key, display_name=meta["display"], response=text)
        except Exception as e:
            return ModelResponse(model_key=model_key, display_name=meta["display"], response="", error=str(e))

    return await asyncio.gather(*[_call(m) for m in active_models])


async def _run_stage2(
    responses: list[ModelResponse], active_models: list[str]
) -> list[ModelResponse]:
    responses_block = _build_responses_block(responses)
    user_prompt = STAGE2_USER_TEMPLATE.format(responses_block=responses_block)

    async def _call(model_key: str) -> ModelResponse:
        meta = providers.MODELS[model_key]
        try:
            text = await providers.complete(model_key, STAGE2_SYSTEM, user_prompt)
            return ModelResponse(model_key=model_key, display_name=meta["display"], response=text)
        except Exception as e:
            return ModelResponse(model_key=model_key, display_name=meta["display"], response="", error=str(e))

    return await asyncio.gather(*[_call(m) for m in active_models])


async def _run_stage3(
    query: str,
    stage1: list[ModelResponse],
    stage2: list[ModelResponse],
    chairman_key: str,
) -> str:
    responses_block = _build_responses_block(stage1)
    reviews_block = _build_reviews_block(stage2)
    user_prompt = STAGE3_USER_TEMPLATE.format(
        query=query,
        responses_block=responses_block,
        reviews_block=reviews_block,
    )
    return await providers.complete(chairman_key, STAGE3_SYSTEM, user_prompt)


async def run_council(
    query: str,
    active_models: list[str],
    chairman_key: str = providers.DEFAULT_CHAIRMAN_KEY,
) -> CouncilResult:
    """
    Entry point. chairman_key is the model that synthesizes in Stage 3.
    active_models should not include the chairman — it only speaks in Stage 3.
    """
    result = CouncilResult(query=query)

    council_models = [m for m in active_models if m != chairman_key]
    if not council_models:
        result.error = "No council members selected. Add at least one non-chairman model."
        return result

    try:
        result.stage1 = await _run_stage1(query, council_models)
        result.stage2 = await _run_stage2(result.stage1, council_models)
        result.chairman_synthesis = await _run_stage3(query, result.stage1, result.stage2, chairman_key)
    except Exception as e:
        result.error = str(e)

    return result
