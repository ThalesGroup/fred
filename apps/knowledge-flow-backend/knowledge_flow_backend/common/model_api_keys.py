# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.

import os
from typing import Literal

from fred_core import ModelProvider
from fred_core.common import ModelConfiguration

ModelRole = Literal["chat", "vision", "embeddings", "ocr"]

_API_KEY_VARIABLES: dict[ModelRole, str] = {
    "chat": "KNOWLEDGE_FLOW_CHAT_API_KEY",
    "vision": "KNOWLEDGE_FLOW_VISION_API_KEY",
    "embeddings": "KNOWLEDGE_FLOW_EMBEDDINGS_API_KEY",
    "ocr": "KNOWLEDGE_FLOW_OCR_API_KEY",
}


def openai_api_key_for_model(config: ModelConfiguration, role: ModelRole) -> str | None:
    if (config.provider or "").lower() != ModelProvider.OPENAI.value:
        return None

    return api_key_for_role(role)


def api_key_for_role(role: ModelRole) -> str:
    dedicated_variable = _API_KEY_VARIABLES[role]
    for variable in (dedicated_variable, "OPENAI_API_KEY"):
        value = os.getenv(variable, "").strip()
        if value:
            return value

    raise ValueError(f"Missing API key for {role} model: set {dedicated_variable} or OPENAI_API_KEY.")
