# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
import os


def reranker_api_key() -> str:
    """Resolve the deployment reranker's credential without changing the environment."""
    variables = ("KNOWLEDGE_FLOW_RERANKER_API_KEY", "OPENAI_API_KEY")
    for variable in variables:
        value = os.getenv(variable, "").strip()
        if value:
            return value
    raise ValueError(f"Missing API key for reranker model: set {' or '.join(variables)}.")
