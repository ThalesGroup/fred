# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""One bounded cosmetic call, within the admitted run and its cleanup scope."""

from __future__ import annotations

import asyncio
import logging
import re

from fred_sdk.contracts.context import BoundRuntimeContext
from fred_sdk.contracts.runtime import RuntimeServices
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.messages import HumanMessage, SystemMessage

from fred_runtime.common.outbound_credentials import get_delegation_runtime
from fred_runtime.model_routing.provider import RoutedChatModelFactory
from fred_runtime.model_routing.turn import current_turn
from fred_runtime.react.middleware.tracing_kpi import TracingKpiMiddleware
from fred_runtime.runtime_context import get_runtime_context
from fred_runtime.runtime_support.model_metadata import runtime_metadata_from_message

logger = logging.getLogger(__name__)
TITLE_TIMEOUT_SECONDS = 10.0
SYSTEM_PROMPT = (
    "You name chat conversations. Reply with the title only: 3 to 8 words, "
    "no quotes, no final punctuation, in the language of the user's message."
)
_NOISE = re.compile(r"[^\w\s'’-]|_")


def clean_title(text: str) -> str | None:
    lines = text.strip().splitlines()
    words = _NOISE.sub(" ", lines[0]).split() if lines else []
    title = " ".join(words)[:80].strip("'’- ")
    return title if any(char.isalpha() for char in title) else None


async def generate_session_title(
    user_input: str, *, binding: BoundRuntimeContext, services: RuntimeServices
) -> str | None:
    """Return the session ID only after its canonical metadata accepted the title."""
    authority = current_turn()
    admitted = authority.binding
    title_admission = admitted.title
    factory = services.chat_model_factory
    if (
        title_admission is None
        or not user_input.strip()
        or not isinstance(factory, RoutedChatModelFactory)
    ):
        return None
    try:
        async with asyncio.timeout(TITLE_TIMEOUT_SECONDS):
            model = factory.build_for_title()
            request = ModelRequest(
                model=model,
                messages=[HumanMessage(content=user_input[:600])],
                system_prompt=SYSTEM_PROMPT,
                tools=[],
            )

            async def invoke(request: ModelRequest) -> ModelResponse:
                reply = await model.ainvoke(
                    [SystemMessage(content=SYSTEM_PROMPT), *request.messages]
                )
                _, usage, _ = runtime_metadata_from_message(reply)
                authority.record_usage(
                    usage, offer=title_admission.inference.selection.key
                )
                return ModelResponse(result=[reply])

            response = await TracingKpiMiddleware(
                tracer=services.tracer,
                kpi=services.kpi_writer,
                binding=binding,
            ).awrap_model_call(request, invoke)
            title = clean_title(response.result[0].text) if response.result else None
            if not title:
                logger.info("event=session_title outcome=skipped reason=invalid_output")
                return None
            authority.check()
            config = get_runtime_context().config
            delegation = get_delegation_runtime()
            client = config.control_plane_http_client
            if delegation is None or client is None or not config.control_plane_url:
                logger.warning(
                    "event=session_title outcome=skipped reason=missing_destination"
                )
                return None
            # Persistence retains admitted provenance. Renewal only refreshes the
            # workload credential; it does not re-admit the person's model rights.
            async with asyncio.timeout(2.0):
                lease = await delegation.workload_token_lease()
                for attempt in range(2):
                    if lease is None:
                        return None
                    result = await client.post(
                        f"{config.control_plane_url.rstrip('/')}/spaces/{admitted.space.id}"
                        f"/sessions/{admitted.conversation_id}/generated-title",
                        json={
                            "subject_id": admitted.subject_id,
                            "agent_instance_id": str(admitted.agent.instance_id),
                            "attempt_id": str(title_admission.attempt_id),
                            "title": title,
                        },
                        headers={"Authorization": f"Bearer {lease.token}"},
                        auth=None,
                        follow_redirects=False,
                    )
                    if result.status_code == 401 and attempt == 0:
                        lease = await delegation.workload_token_lease(rejected=lease)
                        continue
                    logger.info(
                        "event=session_title outcome=%s",
                        "applied" if result.status_code == 204 else "skipped",
                    )
                    return (
                        admitted.conversation_id if result.status_code == 204 else None
                    )
    except Exception as exc:
        # Cosmetic failure must never fail the answer or disclose provider details.
        logger.warning(
            "event=session_title outcome=skipped error_type=%s", type(exc).__name__
        )
    return None
