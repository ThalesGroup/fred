# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Use the platform's default chat model to explain allowlisted filter codes."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Literal

from fred_core.history.content_policy_jobs import (
    ClaimedContentPolicyJob,
    ContentPolicyJobs,
)
from fred_core.history.history_schema import ContentCategory
from fred_sdk.contracts.context import ModelBinding
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field

from fred_runtime.model_routing import RoutedChatModelFactory

logger = logging.getLogger(__name__)
_SYSTEM_PROMPT = (
    "Summarize the confirmed content filter decision using only the structured "
    "evidence provided. Return one allowed explanation code with the supporting "
    "evidence IDs, or return indeterminate. Use only the supplied IDs. Do not infer "
    "a category, content source, or terms-of-use violation."
)


class _Explanation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    explanation_code: ContentCategory | Literal["indeterminate"]
    evidence_ids: list[str] = Field(max_length=11)


async def explain(
    factory: RoutedChatModelFactory, claim: ClaimedContentPolicyJob
) -> ContentCategory | None:
    if not claim.categories:
        return None
    evidence = {
        f"e{index}": category for index, category in enumerate(claim.categories)
    }
    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(
            content=json.dumps(
                {
                    "event": "content_policy_blocked",
                    "filters": [
                        {"id": key, "category": value, "filtered": True}
                        for key, value in evidence.items()
                    ],
                }
            )
        ),
    ]
    try:
        async with asyncio.timeout(6):
            if claim.binding is not None:
                model = factory.build_chat_for_binding(
                    ModelBinding.model_validate(claim.binding)
                )
            else:
                model, _, _ = factory.build_chat_for_profile(claim.pod_profile_id)
            try:
                structured = model.with_structured_output(_Explanation)
            except NotImplementedError:
                instructions = (
                    ' Return only JSON with keys "explanation_code" and "evidence_ids".'
                )
                messages[0] = SystemMessage(content=_SYSTEM_PROMPT + instructions)
                reply = await model.ainvoke(messages)
                if len(reply.text) > 2048:
                    return None
                result = _Explanation.model_validate_json(reply.text)
            else:
                result = _Explanation.model_validate(await structured.ainvoke(messages))
    except Exception as exc:
        logger.info(
            "event=content_policy_analysis_unavailable error_type=%s",
            type(exc).__name__,
        )
        return None
    code = result.explanation_code
    if code == "indeterminate" or not result.evidence_ids:
        return None
    if all(evidence.get(key) == code for key in result.evidence_ids):
        return code
    return None


async def run_content_policy_worker(
    jobs: ContentPolicyJobs, runtime_id: str, factory: RoutedChatModelFactory
) -> None:
    while True:
        try:
            claim = await jobs.claim(runtime_id)
            if claim is not None:
                explanation = await explain(factory, claim)
                await jobs.finish(claim, explanation)
        except Exception as exc:
            logger.warning(
                "event=content_policy_job_failed error_type=%s", type(exc).__name__
            )
        await asyncio.sleep(2)
