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

from datetime import date, datetime

from fred_sdk.contracts.agent_draft import (
    MAX_CREATION_ASSISTANT_PROMPT_CHARS,
    CreationAssistantReasoningEffort,
)
from fred_sdk.contracts.capability.manifest import ReasoningEffortLevel
from fred_sdk.contracts.prompt_utils import find_reserved_prompt_tag
from pydantic import BaseModel, ConfigDict, Field, field_validator

# Generous but finite. The platform prompt is re-sent on every model call of
# every agent on the deployment, so an unbounded field is a live foot-gun:
# 20k characters is already ~5k tokens of permanent context on every turn.
# The admin UI surfaces the same limit so the cost is visible while typing.
PLATFORM_PROMPT_MAX_CHARS = 20_000


class PlatformPrompt(BaseModel):
    """The platform-wide platform prompt as the admin surface reports it."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(
        description=(
            "The platform prompt text currently in force. When `is_default` is "
            "true this is the pod-shipped default (the `platform_prompt` field "
            "of the pod's `config/platform_prompt.json`), which is what agents "
            "actually receive until an admin saves something; when it is false "
            "this is the saved value, and an empty string then means an admin "
            "deliberately suppressed the block."
        )
    )
    is_default: bool = Field(
        description=(
            "True when no row has ever been saved, i.e. `text` is the pod's "
            "default rather than an admin's own. The admin UI uses this to say "
            "'this is the default, save to adopt it' rather than presenting it "
            "as a stored value — and to keep Save enabled on an untouched "
            "default, since adopting it verbatim is a real state change."
        )
    )
    source_unavailable: bool = Field(
        default=False,
        description=(
            "True when `is_default` is true AND no runtime pod could be reached "
            "to report its default, so `text` is empty for lack of an answer "
            "rather than because the default is empty. The UI must say so "
            "instead of showing a blank editor that looks like a real default. "
            "Always false when a row exists — the stored value needs no pod."
        ),
    )
    updated_by: str | None = None
    updated_at: datetime | None = None


class SetPlatformPromptRequest(BaseModel):
    """Org-admin write of the platform-wide platform prompt."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(
        max_length=PLATFORM_PROMPT_MAX_CHARS,
        description=(
            "Replaces the stored platform prompt wholesale. Saving an empty "
            "string is meaningful and supported: it suppresses the block for "
            "every agent, and does NOT restore the pod-shipped default."
        ),
    )

    @field_validator("text")
    @classmethod
    def _refuse_reserved_tags(cls, value: str) -> str:
        # The runtime wraps this text in <platform_prompt>; a reserved tag
        # inside it could close that block and open another.
        return _refuse_reserved_tags(value, "the platform prompt")


def _refuse_reserved_tags(value: str, where: str) -> str:
    reserved = find_reserved_prompt_tag(value)
    if reserved is not None:
        raise ValueError(
            f"reserved system-prompt tag <{reserved}> is not allowed in {where}"
        )
    return value


class PlatformInstructions(BaseModel):
    """The platform's read-only operating instructions, as the admin UI shows them.

    Not editable, by design: an admin can rewrite the platform prompt above it
    freely, and the behaviour a coherent platform depends on (call the tools you
    were given, never fake a call, recover from a failed one) must not be
    rewritable along with it. The text ships with the pod
    (`config/platform_prompt.json`, field `platform_instructions`), so there is no
    row, no `updated_by`, and no PUT — exposing it is about letting an admin see
    exactly what every agent is told, not about changing it. It reaches
    control-plane over the pod's `GET /agents/platform-prompt`, since the file
    lives with the pod that composes it.
    """

    model_config = ConfigDict(extra="forbid")

    text: str = Field(
        description=(
            "Markdown rendered verbatim as the second block of every agent's "
            "system prompt, immediately under the platform prompt. Empty when "
            "`source_unavailable` is true."
        )
    )
    source_unavailable: bool = Field(
        default=False,
        description=(
            "True when no runtime pod could be reached to report its shipped "
            "instructions. `text` is then empty for lack of an answer, not "
            "because agents receive no instructions — the UI must distinguish "
            "the two rather than render an empty read-only panel."
        ),
    )


# The creation assistant substitutes the user's language here; without it the
# draft may come back in the wrong language.
CREATION_ASSISTANT_LANGUAGE_PLACEHOLDER = "{language}"


class CreationAssistantModelOption(BaseModel):
    """A chat profile the creation assistant may use."""

    profile_id: str
    name: str = Field(description="Catalog model name, for display.")
    supports_reasoning: bool = Field(
        default=False,
        description=(
            "True when this profile declares `supports_thinking` and has a "
            "reasoning effort the pod can send."
        ),
    )
    reasoning_efforts: list[ReasoningEffortLevel] = Field(
        default_factory=list,
        description=(
            "Selectable reasoning levels, weakest first; empty for an on/off "
            "profile (or one that cannot reason)."
        ),
    )


class CreationAssistantSettings(BaseModel):
    """The creation assistant's settings as the admin surface reports them."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(
        description=(
            "The meta-prompt in force: the saved override, or the pod default "
            "when `is_default` is true (empty if no pod could be reached)."
        )
    )
    default_text: str | None = Field(
        default=None,
        description="The pod's built-in meta-prompt; None when no pod answered.",
    )
    default_revised_at: date | None = Field(
        default=None,
        description="Date of the last edit of the built-in meta-prompt; None for an older or unreachable pod.",
    )
    default_changed_since_override: bool = Field(
        default=False,
        description=(
            "True when an override is saved and the built-in meta-prompt was "
            "revised on a later date. The admin UI shows it as a warning."
        ),
    )
    is_default: bool = Field(description="True when no override is saved.")
    source_unavailable: bool = Field(
        default=False,
        description="True when no runtime pod could report its built-in meta-prompt.",
    )
    missing_language_placeholder: bool = Field(
        default=False,
        description=(
            "True when `text` lacks the `{language}` placeholder. Saving is "
            "allowed; the admin UI shows it as a warning."
        ),
    )
    model_profile_id: str | None = Field(
        default=None,
        description="Chat profile the creation assistant uses; None = the pod default.",
    )
    reasoning_effort: CreationAssistantReasoningEffort = Field(
        default="off",
        description=(
            "Reasoning of the assistant's own call. Any non-'off' value means "
            "on for an on/off profile; a level the profile does not offer is "
            "clamped by the pod to the nearest one."
        ),
    )
    default_model_profile_id: str | None = Field(
        default=None,
        description=(
            "The pods' default chat profile, when every reachable pod names "
            "the same one; tells the UI which reasoning control the platform "
            "default offers."
        ),
    )
    model_options: list[CreationAssistantModelOption] = Field(
        default_factory=list,
        description="Chat profiles every enabled pod advertises; empty when none answered.",
    )
    updated_by: str | None = None
    updated_at: datetime | None = None


class SetCreationAssistantSettingsRequest(BaseModel):
    """Replaces the creation assistant settings. DELETE clears `text` only."""

    model_config = ConfigDict(extra="forbid")

    text: str | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_CREATION_ASSISTANT_PROMPT_CHARS,
        description="Meta-prompt override; None keeps the pod's built-in text.",
    )
    model_profile_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="One of `model_options`; None uses the pod default.",
    )
    reasoning_effort: CreationAssistantReasoningEffort = Field(
        default="off",
        description="Reasoning of the assistant's call; clamped to the model by the pod.",
    )

    @field_validator("text")
    @classmethod
    def _validate(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.strip():
            raise ValueError("the creation assistant prompt cannot be blank")
        return _refuse_reserved_tags(value, "the creation assistant prompt")
