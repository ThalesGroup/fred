# Copyright Thales 2025
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

from types import SimpleNamespace

import pytest
from fred_core import ModelConfiguration

import knowledge_flow_backend.application_context as application_context_module
from knowledge_flow_backend.application_context import ApplicationContext


@pytest.fixture(scope="function", autouse=True)
def app_context():
    # Override global autouse fixture from tests/conftest.py for this module.
    ApplicationContext._instance = None
    yield
    ApplicationContext._instance = None


def _build_context(model_name: str, settings: dict) -> ApplicationContext:
    ctx = ApplicationContext.__new__(ApplicationContext)
    ctx.configuration = SimpleNamespace(
        crossencoder_model=ModelConfiguration(
            provider=None,
            name=model_name,
            settings=settings,
        )
    )
    return ctx


def test_get_crossencoder_model_offline_uses_resolved_local_path(monkeypatch, tmp_path):
    cache_path = tmp_path / ".hf-cache"
    cache_path.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(tmp_path))

    calls: list[dict] = []

    def fake_cross_encoder(*, model_name_or_path, cache_folder=None, local_files_only=None):
        calls.append(
            {
                "model_name_or_path": model_name_or_path,
                "cache_folder": cache_folder,
                "local_files_only": local_files_only,
            }
        )
        return SimpleNamespace(
            model_name_or_path=model_name_or_path,
            cache_folder=cache_folder,
            local_files_only=local_files_only,
        )

    monkeypatch.setattr(application_context_module, "CrossEncoder", fake_cross_encoder)

    context = _build_context(
        model_name="cross-encoder/ms-marco-MiniLM-L-12-v2",
        settings={"online": False, "local_path": "~/.hf-cache"},
    )

    model = ApplicationContext.get_crossencoder_model(context)

    assert model.cache_folder == str(cache_path.resolve())
    assert model.local_files_only is True
    assert len(calls) == 1
    assert calls[0]["cache_folder"] == str(cache_path.resolve())


def test_get_crossencoder_model_offline_raises_when_local_path_load_fails(monkeypatch, tmp_path):
    configured_path = tmp_path / "missing-cache"
    expected_local_path = str(configured_path.resolve())

    calls: list[str | None] = []

    def fake_cross_encoder(*, model_name_or_path, cache_folder=None, local_files_only=None):
        calls.append(cache_folder)
        raise RuntimeError("configured cache missing")

    monkeypatch.setattr(application_context_module, "CrossEncoder", fake_cross_encoder)

    context = _build_context(
        model_name="cross-encoder/ms-marco-MiniLM-L-12-v2",
        settings={"online": False, "local_path": str(configured_path)},
    )

    with pytest.raises(ValueError) as exc_info:
        ApplicationContext.get_crossencoder_model(context)

    message = str(exc_info.value)
    assert "from local_path" in message
    assert expected_local_path in message
    assert calls == [expected_local_path]


def test_get_crossencoder_model_offline_raises_when_local_path_missing():
    context = _build_context(
        model_name="cross-encoder/ms-marco-MiniLM-L-12-v2",
        settings={"online": False},
    )

    with pytest.raises(ValueError) as exc_info:
        ApplicationContext.get_crossencoder_model(context)

    message = str(exc_info.value)
    assert "local cross-encoder model is required for offline mode" in message


def test_get_crossencoder_model_online_behavior_unchanged(monkeypatch):
    calls: list[dict] = []

    def fake_cross_encoder(*, model_name_or_path, cache_folder=None, local_files_only=None):
        calls.append(
            {
                "model_name_or_path": model_name_or_path,
                "cache_folder": cache_folder,
                "local_files_only": local_files_only,
            }
        )
        return SimpleNamespace(
            model_name_or_path=model_name_or_path,
            cache_folder=cache_folder,
            local_files_only=local_files_only,
        )

    monkeypatch.setattr(application_context_module, "CrossEncoder", fake_cross_encoder)

    context = _build_context(
        model_name="cross-encoder/ms-marco-MiniLM-L-12-v2",
        settings={"online": True, "local_path": "~/.cache/huggingface"},
    )

    model = ApplicationContext.get_crossencoder_model(context)

    assert model.cache_folder is None
    assert model.local_files_only is None
    assert len(calls) == 1
    assert calls[0]["cache_folder"] is None
    assert calls[0]["local_files_only"] is None
