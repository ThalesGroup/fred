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

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

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
