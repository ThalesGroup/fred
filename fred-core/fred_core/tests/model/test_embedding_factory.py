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

import sys
from types import ModuleType
from typing import Any

from fred_core.common import ModelConfiguration
from fred_core.model.factory import get_embeddings


def test_get_embeddings_vertex_model_garden_uses_full_vertex_model_name(
    monkeypatch: Any,
) -> None:
    calls: list[dict[str, Any]] = []

    class _FakeGoogleGenerativeAIEmbeddings:
        def __init__(self, **kwargs: Any) -> None:
            calls.append(kwargs)

    fake_module = ModuleType("langchain_google_genai")
    setattr(
        fake_module,
        "GoogleGenerativeAIEmbeddings",
        _FakeGoogleGenerativeAIEmbeddings,
    )
    monkeypatch.setitem(sys.modules, "langchain_google_genai", fake_module)

    cfg = ModelConfiguration(
        provider="vertex-ai-model-garden",
        name="publishers/baai/models/bge-m3",
        settings={
            "project": "demo-project",
            "location": "europe-west1",
            "max_retries": 2,
            "request_timeout": 90,
            "model_family": "embedding",
        },
    )

    model = get_embeddings(cfg)

    assert isinstance(model, _FakeGoogleGenerativeAIEmbeddings)
    assert calls == [
        {
            "model": "publishers/baai/models/bge-m3",
            "project": "demo-project",
            "location": "europe-west1",
            "vertexai": True,
            "max_retries": 2,
        }
    ]
