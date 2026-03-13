"""
Default policy bootstrap from Fred's existing AI configuration.

This lets teams start with model routing without changing YAML structure first.
"""

from __future__ import annotations

from fred_core import ModelConfiguration
from pydantic import Field

from agentic_backend.common.structures import AIConfig

from .contracts import (
    FrozenModel,
    ModelCapability,
    ModelProfile,
    ModelRoutingPolicy,
)


class DefaultRoutingProfileIds(FrozenModel):
    """
    Stable profile ids used by the default bootstrap policy.
    """

    chat: str = Field(default="default.chat", min_length=1)
    language: str = Field(default="default.language", min_length=1)
    embedding: str = Field(default="default.embedding", min_length=1)
    image: str = Field(default="default.image", min_length=1)


def build_default_policy_from_ai_config(
    *,
    ai_config: AIConfig,
    profile_ids: DefaultRoutingProfileIds | None = None,
    default_embedding_model: ModelConfiguration | None = None,
    default_image_model: ModelConfiguration | None = None,
) -> ModelRoutingPolicy:
    """
    Build a minimal multi-capability routing policy from current Fred config.

    Source mapping:
    - `ai.default_chat_model` -> capability `chat`
    - `ai.default_language_model` (or fallback chat) -> capability `language`
    - embeddings/image are optional explicit parameters for now

    This avoids touching configuration schema while establishing the policy
    contract and resolver semantics.
    """

    if ai_config.default_chat_model is None:
        raise ValueError(
            "ai.default_chat_model is required to bootstrap default routing policy."
        )

    ids = profile_ids or DefaultRoutingProfileIds()
    default_chat_model = ai_config.default_chat_model.model_copy(deep=True)
    profiles: list[ModelProfile] = [
        ModelProfile(
            profile_id=ids.chat,
            capability=ModelCapability.CHAT,
            model=default_chat_model.model_copy(deep=True),
            description="Default chat model from ai.default_chat_model",
        ),
        ModelProfile(
            profile_id=ids.language,
            capability=ModelCapability.LANGUAGE,
            model=(
                ai_config.default_language_model.model_copy(deep=True)
                if ai_config.default_language_model is not None
                else default_chat_model.model_copy(deep=True)
            ),
            description=(
                "Default language model from ai.default_language_model "
                "(fallback to ai.default_chat_model when missing)."
            ),
        ),
    ]

    defaults_by_capability: dict[ModelCapability, str] = {
        ModelCapability.CHAT: ids.chat,
        ModelCapability.LANGUAGE: ids.language,
    }

    if default_embedding_model is not None:
        profiles.append(
            ModelProfile(
                profile_id=ids.embedding,
                capability=ModelCapability.EMBEDDING,
                model=default_embedding_model.model_copy(deep=True),
                description="Default embedding model from bootstrap parameter.",
            )
        )
        defaults_by_capability[ModelCapability.EMBEDDING] = ids.embedding

    if default_image_model is not None:
        profiles.append(
            ModelProfile(
                profile_id=ids.image,
                capability=ModelCapability.IMAGE,
                model=default_image_model.model_copy(deep=True),
                description="Default image model from bootstrap parameter.",
            )
        )
        defaults_by_capability[ModelCapability.IMAGE] = ids.image

    return ModelRoutingPolicy(
        default_profile_by_capability=defaults_by_capability,
        profiles=tuple(profiles),
        rules=(),
    )
