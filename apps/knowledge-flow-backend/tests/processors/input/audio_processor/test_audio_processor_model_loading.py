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
Whisper model loading must stay offline-first (issue #2406).

The knowledge-flow prod image bakes the Whisper model into the Hugging Face hub
cache and runs with HF_HUB_OFFLINE=1, so `_get_model()` has to resolve the model
from the local cache first, ask for the very model size the image baked, and only
reach for a hub download when that local load fails.
"""

from types import SimpleNamespace

from knowledge_flow_backend.core.processors.input.audio_processor.audio_processor import AudioProcessor


def test_get_model_prefers_local_cache(monkeypatch):
    calls: list[dict] = []

    def fake_whisper_model(model_size_or_path, **kwargs):
        calls.append({"model_size_or_path": model_size_or_path, **kwargs})
        return SimpleNamespace(name=model_size_or_path)

    monkeypatch.delenv("WHISPER_MODEL_SIZE", raising=False)
    monkeypatch.setattr("faster_whisper.WhisperModel", fake_whisper_model)

    model = AudioProcessor()._get_model()

    assert calls == [
        {
            "model_size_or_path": "base",
            "device": "cpu",
            "compute_type": "int8",
            "local_files_only": True,
        }
    ]
    assert model.name == "base"


def test_get_model_falls_back_to_download_when_not_cached(monkeypatch):
    calls: list[dict] = []

    def fake_whisper_model(model_size_or_path, **kwargs):
        calls.append({"model_size_or_path": model_size_or_path, **kwargs})
        if kwargs.get("local_files_only"):
            raise RuntimeError("model not found in local cache")
        return SimpleNamespace(name=model_size_or_path)

    monkeypatch.delenv("WHISPER_MODEL_SIZE", raising=False)
    monkeypatch.setattr("faster_whisper.WhisperModel", fake_whisper_model)

    processor = AudioProcessor()
    model = processor._get_model()

    assert len(calls) == 2
    assert calls[0]["local_files_only"] is True
    assert "local_files_only" not in calls[1]
    assert calls[1] == {"model_size_or_path": "base", "device": "cpu", "compute_type": "int8"}
    assert model.name == "base"

    # The resolved model is cached: a second call must not re-instantiate it.
    assert processor._get_model() is model
    assert len(calls) == 2


def test_get_model_requests_the_model_size_baked_into_the_image(monkeypatch):
    """The prod image bakes WHISPER_MODEL_SIZE; the runtime must ask for that same model."""
    calls: list[dict] = []

    def fake_whisper_model(model_size_or_path, **kwargs):
        calls.append({"model_size_or_path": model_size_or_path, **kwargs})
        return SimpleNamespace(name=model_size_or_path)

    monkeypatch.setenv("WHISPER_MODEL_SIZE", "small")
    monkeypatch.setattr("faster_whisper.WhisperModel", fake_whisper_model)

    model = AudioProcessor()._get_model()

    assert [call["model_size_or_path"] for call in calls] == ["small"]
    assert model.name == "small"
