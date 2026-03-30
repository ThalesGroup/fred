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

"""
Basic ReAct model-routing presets.

Business/profile-specific routing rules live here (agent layer), while
`core.agents.v2.model_routing` remains generic.
"""

from __future__ import annotations

from fred_core.common import ModelConfiguration
from pydantic import Field

from agentic_backend.common.structures import AIConfig
from agentic_backend.core.agents.v2.model_routing import (
    DefaultRoutingProfileIds,
    ModelCapability,
    ModelProfile,
    ModelRouteMatch,
    ModelRouteRule,
    ModelRoutingPolicy,
    build_default_policy_from_ai_config,
)
from agentic_backend.core.agents.v2.model_routing.contracts import FrozenModel


class BasicReActPresetProfileIds(FrozenModel):
    """
    Registry of Profile IDs that have special model requirements.
    """

    log_genius_chat: str = Field(default="preset.chat.log_genius", min_length=1)
    rag_expert_chat: str = Field(default="preset.chat.rag_expert", min_length=1)


class BasicReActPresetRuleIds(FrozenModel):
    """
    Internal IDs for the routing rules defined in this file.
    """

    log_genius_chat: str = Field(default="preset.log_genius.chat", min_length=1)
    rag_expert_chat: str = Field(default="preset.rag_expert.chat", min_length=1)


def build_default_policy_with_basic_react_presets(
    *,
    ai_config: AIConfig,
    profile_ids: DefaultRoutingProfileIds | None = None,
    preset_profile_ids: BasicReActPresetProfileIds | None = None,
    preset_rule_ids: BasicReActPresetRuleIds | None = None,
    log_genius_chat_model: ModelConfiguration | None = None,
    rag_expert_chat_model: ModelConfiguration | None = None,
    default_embedding_model: ModelConfiguration | None = None,
    default_image_model: ModelConfiguration | None = None,
) -> ModelRoutingPolicy:
    """
    Construct the routing policy, wiring specific profiles to specific models.
    """

    base = build_default_policy_from_ai_config(
        ai_config=ai_config,
        profile_ids=profile_ids,
        default_embedding_model=default_embedding_model,
        default_image_model=default_image_model,
    )
    if ai_config.default_chat_model is None:
        raise ValueError(
            "ai.default_chat_model is required to build Basic ReAct presets."
        )
    resolved_preset_profile_ids = preset_profile_ids or BasicReActPresetProfileIds()
    resolved_preset_rule_ids = preset_rule_ids or BasicReActPresetRuleIds()

    # 1. Resolve which models to use (Config vs Defaults)
    resolved_log_genius_model = (
        log_genius_chat_model.model_copy(deep=True)
        if log_genius_chat_model is not None
        else (
            ai_config.default_language_model.model_copy(deep=True)
            if ai_config.default_language_model is not None
            else ai_config.default_chat_model.model_copy(deep=True)
        )
    )
    resolved_rag_expert_model = (
        rag_expert_chat_model.model_copy(deep=True)
        if rag_expert_chat_model is not None
        else ai_config.default_chat_model.model_copy(deep=True)
    )

    profiles = list(base.profiles)
    rules = list(base.rules)

    # 2. Add Rule: LogGenius uses the fast/cheap model
    profiles.append(
        ModelProfile(
            profile_id=resolved_preset_profile_ids.log_genius_chat,
            capability=ModelCapability.CHAT,
            model=resolved_log_genius_model,
            description=(
                "Preset for internal LogGenius profile "
                "(fast monitoring and trace triage)."
            ),
        )
    )
    rules.append(
        ModelRouteRule(
            rule_id=resolved_preset_rule_ids.log_genius_chat,
            capability=ModelCapability.CHAT,
            target_profile_id=resolved_preset_profile_ids.log_genius_chat,
            match=ModelRouteMatch(
                purpose="chat",
                agent_id="internal.react_profile.log_genius",
            ),
        )
    )

    # 3. Add Rule: RAG Expert uses the smart/grounded model
    profiles.append(
        ModelProfile(
            profile_id=resolved_preset_profile_ids.rag_expert_chat,
            capability=ModelCapability.CHAT,
            model=resolved_rag_expert_model,
            description=(
                "Preset for RAG Expert profile "
                "(document-grounded synthesis and response quality)."
            ),
        )
    )
    rules.append(
        ModelRouteRule(
            rule_id=resolved_preset_rule_ids.rag_expert_chat,
            capability=ModelCapability.CHAT,
            target_profile_id=resolved_preset_profile_ids.rag_expert_chat,
            match=ModelRouteMatch(
                purpose="chat",
                agent_id="internal.react_profile.rag_expert",
            ),
        )
    )

    return ModelRoutingPolicy(
        default_profile_by_capability=dict(base.default_profile_by_capability),
        profiles=tuple(profiles),
        rules=tuple(rules),
    )
