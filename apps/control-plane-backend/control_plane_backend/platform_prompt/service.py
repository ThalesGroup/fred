# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx
from fred_core import KeycloakUser

from control_plane_backend.organization_authz import require_manage_any
from control_plane_backend.platform_prompt.schemas import (
    PlatformInstructions,
    PlatformPrompt,
)
from control_plane_backend.platform_prompt.store import StoredPlatformPrompt
from control_plane_backend.product.dependencies import ProductServiceDependencies

logger = logging.getLogger(__name__)

# Same timeout as every other pod fetch on this side (`_fetch_mcp_catalog`,
# `_model_capabilities_for_source`): this is an admin page load, not a turn.
_POD_FETCH_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class PodPlatformPromptFile:
    """One pod's `config/platform_prompt.json`, as `/agents/platform-prompt`
    reports it."""

    platform_prompt: str
    platform_instructions: str


async def fetch_pod_platform_prompt_file(
    deps: ProductServiceDependencies,
) -> PodPlatformPromptFile | None:
    """Fetch the platform-prompt file from the first runtime pod that answers.

    Why this exists:
    - both head blocks are pod-shipped config, and control-plane runs in a
      different container — it cannot read the pod's filesystem. This is the
      same shape `/agents/models-catalog` already uses for `models_catalog.yaml`
      (`product/service._model_capabilities_for_source`).

    First reachable pod wins rather than merging across pods: these two blocks
    are platform-wide, every pod runs the same image, and there is no meaningful
    way to reconcile two pods that shipped different text. A deployment that
    somehow does will show the first source's copy — the alternative, fetching
    all of them to detect disagreement, buys a warning nobody can act on from
    this page.

    Returns `None` when no pod answers. Callers must not substitute an empty
    string for that: "the pod says the block is empty" and "we could not ask"
    are different things to show an admin.
    """

    for source in deps.configuration.platform.runtime_catalog_sources:
        url = f"{source.base_url.rstrip('/')}/agents/platform-prompt"
        try:
            async with httpx.AsyncClient(timeout=_POD_FETCH_TIMEOUT_SECONDS) as client:
                response = await client.get(url)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            # WARNING, not DEBUG: with no pod reachable the admin page cannot
            # show what agents are actually told, which is the whole point of
            # the page. Also covers a pod predating this route (404).
            logger.warning(
                "[platform-prompt] failed to fetch platform prompt file from %s: %s",
                source.base_url,
                exc,
            )
            continue
        return PodPlatformPromptFile(
            platform_prompt=str(payload.get("platform_prompt", "")),
            platform_instructions=str(payload.get("platform_instructions", "")),
        )
    return None


def _to_platform_prompt(
    stored: StoredPlatformPrompt | None,
    pod_default: str | None = None,
) -> PlatformPrompt:
    """Project the stored row for the admin surface.

    `pod_default` is the `platform_prompt` field of the pod's
    `config/platform_prompt.json`, or `None` when no pod could be reached. It is
    used ONLY when there is no row: reporting an empty string there is what made
    the admin page show a blank editor on a fresh deployment, implying no
    platform prompt was in force when the pods were already running on one.
    """

    if stored is None:
        # `is_default` still marks it as unsaved, which is what lets the UI say
        # "this is the shipped default, save to adopt it" and keeps Save enabled.
        return PlatformPrompt(
            text=pod_default or "",
            is_default=True,
            source_unavailable=pod_default is None,
        )
    # A saved row is authoritative on its own; the pod file is irrelevant to it,
    # including when it is an empty string an admin saved deliberately.
    return PlatformPrompt(
        text=stored.text,
        is_default=False,
        updated_by=stored.updated_by,
        updated_at=stored.updated_at,
    )


async def get_platform_prompt(
    *, user: KeycloakUser, deps: ProductServiceDependencies
) -> PlatformPrompt:
    """Org-admin-gated read of the platform-wide platform prompt."""

    await require_manage_any(deps.team_dependencies.rebac, user)
    stored = await deps.get_platform_prompt_store().get()
    if stored is not None:
        # A saved row answers the question by itself — skip the pod round-trip.
        return _to_platform_prompt(stored)
    pod_file = await fetch_pod_platform_prompt_file(deps)
    return _to_platform_prompt(
        stored, pod_default=pod_file.platform_prompt if pod_file else None
    )


async def set_platform_prompt(
    *, user: KeycloakUser, text: str, deps: ProductServiceDependencies
) -> PlatformPrompt:
    """Org-admin-gated write of the platform-wide platform prompt.

    `text` arrives length-checked by `SetPlatformPromptRequest` at
    request-parsing time. Saving `""` is a supported, meaningful operation —
    it suppresses the block platform-wide — so there is no "empty means
    delete" shortcut here.
    """

    await require_manage_any(deps.team_dependencies.rebac, user)
    stored = await deps.get_platform_prompt_store().set(text=text, updated_by=user.uid)
    return _to_platform_prompt(stored)


async def resolve_platform_prompt_text(
    deps: ProductServiceDependencies,
) -> str | None:
    """Return the stored platform prompt for a runtime binding, or `None`.

    Why this exists:
    - the runtime needs this on EVERY managed turn, and must not be gated on
      the caller's authorization: this is a platform assertion, resolved
      server-side, exactly like `resolve_platform_chat_model_binding`. Passing
      a user here would be the bug, not the omission.

    `None` means no admin has ever saved one; the pod then falls back to its
    own `config/platform_prompt.json`. A stored `""` returns `""`, which
    suppresses the block — the two are deliberately distinguishable.

    Note the asymmetry with `get_platform_prompt` above, which substitutes the
    default into its response: that one describes the deployment to a human,
    this one carries an admin decision to the runtime. Substituting here would
    send the pod a value it already has, and would erase the very distinction
    the runtime needs to honour a deliberate `""`.
    """

    stored = await deps.get_platform_prompt_store().get()
    return None if stored is None else stored.text


async def get_platform_instructions(
    *, user: KeycloakUser, deps: ProductServiceDependencies
) -> PlatformInstructions:
    """Org-admin-gated read of the shipped, read-only platform instructions.

    Gated like its editable sibling even though it reveals nothing secret: it is
    an `/admin/platform/...` route, and keeping one permission for the whole
    surface is easier to reason about than two. Reads the same pod file the
    runtime composes into every prompt, so the UI cannot drift from what agents
    are actually told — and reports `source_unavailable` rather than an empty
    block when no pod answers, since "no instructions" would be a lie.
    """

    await require_manage_any(deps.team_dependencies.rebac, user)
    pod_file = await fetch_pod_platform_prompt_file(deps)
    if pod_file is None:
        return PlatformInstructions(text="", source_unavailable=True)
    return PlatformInstructions(text=pod_file.platform_instructions)
