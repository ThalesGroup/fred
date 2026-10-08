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
from collections import Counter
from dataclasses import dataclass
from datetime import date

import httpx
from fastapi import HTTPException
from fred_core import KeycloakUser
from fred_sdk.contracts.agent_draft import CreationAssistantReasoningEffort

from control_plane_backend.capabilities.catalog import (
    aggregate_capability_catalog,
    universally_available_chat_model_profile_ids,
)
from control_plane_backend.organization_authz import require_edit_platform_prompt
from control_plane_backend.platform_prompt.schemas import (
    CREATION_ASSISTANT_LANGUAGE_PLACEHOLDER,
    CreationAssistantModelOption,
    CreationAssistantSettings,
    PlatformInstructions,
    PlatformPrompt,
)
from control_plane_backend.platform_prompt.store import (
    StoredCreationAssistantSettings,
    StoredPlatformPrompt,
)
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
    # None for a pod that predates the creation assistant override.
    creation_assistant_prompt: str | None = None
    creation_assistant_prompt_revised_at: date | None = None


def _parse_revision_date(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value)) if value else None
    except ValueError:
        return None


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
            creation_assistant_prompt=(
                str(payload["creation_assistant_prompt"])
                if payload.get("creation_assistant_prompt") is not None
                else None
            ),
            creation_assistant_prompt_revised_at=_parse_revision_date(
                payload.get("creation_assistant_prompt_revised_at")
            ),
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
    """`can_edit_platform_prompt`-gated read of the platform-wide prompt.

    Same gate as the write below, not a laxer one: an editor who cannot read
    what they are about to overwrite is useless, and this was never readable
    below the admin tier anyway.
    """

    await require_edit_platform_prompt(deps.team_dependencies.rebac, user)
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
    """`can_edit_platform_prompt`-gated write of the platform-wide prompt.

    `text` arrives length-checked by `SetPlatformPromptRequest` at
    request-parsing time. Saving `""` is a supported, meaningful operation —
    it suppresses the block platform-wide — so there is no "empty means
    delete" shortcut here.
    """

    await require_edit_platform_prompt(deps.team_dependencies.rebac, user)
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
    """`can_edit_platform_prompt`-gated read of the shipped instructions.

    Gated like its editable sibling even though it reveals nothing secret: it is
    an `/admin/platform/...` route, and keeping one permission for the whole
    surface is easier to reason about than two — and this pane is the reference
    an editor needs to know what agents are already told. Reads the same pod file the
    runtime composes into every prompt, so the UI cannot drift from what agents
    are actually told — and reports `source_unavailable` rather than an empty
    block when no pod answers, since "no instructions" would be a lie.
    """

    await require_edit_platform_prompt(deps.team_dependencies.rebac, user)
    pod_file = await fetch_pod_platform_prompt_file(deps)
    if pod_file is None:
        return PlatformInstructions(text="", source_unavailable=True)
    return PlatformInstructions(text=pod_file.platform_instructions)


async def get_creation_assistant_settings(
    *, user: KeycloakUser, deps: ProductServiceDependencies
) -> CreationAssistantSettings:
    """`can_edit_platform_prompt`-gated read of the creation assistant settings.

    Always asks the pods, even with an override saved: the editor shows the
    default it would reset to and the models it may choose."""

    await require_edit_platform_prompt(deps.team_dependencies.rebac, user)
    return await _project_creation_assistant_settings(deps)


async def set_creation_assistant_settings(
    *,
    user: KeycloakUser,
    text: str | None,
    model_profile_id: str | None,
    reasoning_effort: CreationAssistantReasoningEffort = "off",
    deps: ProductServiceDependencies,
) -> CreationAssistantSettings:
    await require_edit_platform_prompt(deps.team_dependencies.rebac, user)
    store = deps.get_creation_assistant_settings_store()
    stored = await store.get()
    # The stored choice stays valid as is: a catalog change, or no pod
    # answering, must not block saving the text. The reasoning effort is not
    # checked against the model: the pod clamps it (design.md decision 14).
    unchanged = stored is not None and stored.model_profile_id == model_profile_id
    if model_profile_id is not None and not unchanged:
        options = await creation_assistant_model_options(deps)
        if model_profile_id not in {o.profile_id for o in options}:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown chat model profile {model_profile_id!r}.",
            )
    await store.set(
        text=text,
        model_profile_id=model_profile_id,
        reasoning_effort=reasoning_effort,
        updated_by=user.uid,
    )
    return await _project_creation_assistant_settings(deps)


async def reset_creation_assistant_prompt(
    *, user: KeycloakUser, deps: ProductServiceDependencies
) -> CreationAssistantSettings:
    """Clears the meta-prompt override; the model and reasoning are kept."""
    await require_edit_platform_prompt(deps.team_dependencies.rebac, user)
    store = deps.get_creation_assistant_settings_store()
    stored = await store.get()
    if stored is not None and stored.text is not None:
        await store.set(
            text=None,
            model_profile_id=stored.model_profile_id,
            reasoning_effort=stored.reasoning_effort,
            updated_by=user.uid,
        )
    return await _project_creation_assistant_settings(deps)


async def creation_assistant_model_options(
    deps: ProductServiceDependencies,
) -> list[CreationAssistantModelOption]:
    """Chat profiles every enabled pod advertises, the same set team routing
    may pick from, named after their catalog model."""
    return (await _creation_assistant_models(deps))[0]


async def _creation_assistant_models(
    deps: ProductServiceDependencies,
) -> tuple[list[CreationAssistantModelOption], str | None]:
    """The model options and the pods' common default chat profile, if any."""

    # Lazy: product.service imports this package's dependencies.
    from control_plane_backend.product.service import (
        _model_capabilities_for_source,
        _pod_catalog_fetch_scope,
    )

    with _pod_catalog_fetch_scope():
        catalog = await aggregate_capability_catalog(deps)
        universal = await universally_available_chat_model_profile_ids(deps)
        defaults: set[str | None] = set()
        for source in deps.configuration.platform.runtime_catalog_sources:
            if source.enabled:
                pod = await _model_capabilities_for_source(source.base_url)
                if pod is not None and pod.entries:
                    defaults.add(pod.default_chat_profile_id)
    named = {
        profile_id: entry.model_display_name or entry.name
        for entry in catalog.values()
        if entry.kind == "model"
        for profile_id in entry.model_chat_profile_ids
        if profile_id in universal
    }
    thinking = {
        profile_id
        for entry in catalog.values()
        if entry.kind == "model"
        for profile_id in entry.model_thinking_profile_ids
    }
    levels = {
        profile_id: list(profile_levels)
        for entry in catalog.values()
        if entry.kind == "model"
        for profile_id, profile_levels in entry.model_reasoning_efforts.items()
    }
    names = Counter(named.values())
    options = sorted(
        (
            CreationAssistantModelOption(
                profile_id=profile_id,
                # Two profiles of one model are told apart by their id.
                name=name if names[name] == 1 else f"{name} ({profile_id})",
                # Empty levels: a thinking profile the pod cannot make reason.
                supports_reasoning=profile_id in thinking
                and levels.get(profile_id) != [],
                reasoning_efforts=levels.get(profile_id, [])
                if profile_id in thinking
                else [],
            )
            for profile_id, name in named.items()
        ),
        key=lambda option: option.name.lower(),
    )
    # Pods disagreeing (or none answering) leave the default unknown.
    default = defaults.pop() if len(defaults) == 1 else None
    return options, default


async def _project_creation_assistant_settings(
    deps: ProductServiceDependencies,
) -> CreationAssistantSettings:
    stored = await deps.get_creation_assistant_settings_store().get()
    override = stored.text if stored is not None else None
    pod_file = await fetch_pod_platform_prompt_file(deps)
    default = pod_file.creation_assistant_prompt if pod_file else None
    revised_at = pod_file.creation_assistant_prompt_revised_at if pod_file else None
    text = override if override is not None else (default or "")
    model_options, default_profile_id = await _creation_assistant_models(deps)
    # Day granularity: the pod only dates its default, not the hour of the edit.
    changed = (
        override is not None
        and stored is not None
        and stored.updated_at is not None
        and revised_at is not None
        and revised_at > stored.updated_at.date()
    )
    return CreationAssistantSettings(
        text=text,
        default_text=default,
        default_revised_at=revised_at,
        default_changed_since_override=changed,
        is_default=override is None,
        source_unavailable=default is None,
        missing_language_placeholder=bool(text)
        and CREATION_ASSISTANT_LANGUAGE_PLACEHOLDER not in text,
        model_profile_id=stored.model_profile_id if stored else None,
        reasoning_effort=stored.reasoning_effort if stored else "off",
        default_model_profile_id=default_profile_id,
        model_options=model_options,
        updated_by=stored.updated_by if stored else None,
        updated_at=stored.updated_at if stored else None,
    )


async def resolve_creation_assistant_settings(
    deps: ProductServiceDependencies,
) -> StoredCreationAssistantSettings | None:
    """The saved settings for the pod, or None (pod defaults). Not user-gated:
    any agent editor's draft must use the admin's settings."""

    return await deps.get_creation_assistant_settings_store().get()
