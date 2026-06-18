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

from pathlib import Path

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from fred_core import KeycloakUser, get_current_user

from knowledge_flow_backend.features.audio.audio_transcription_controller import (
    AudioTranscriptionController,
)
from knowledge_flow_backend.features.audio.audio_transcription_service import (
    MAX_AUDIO_TRANSCRIPTION_BYTES,
)


@pytest.fixture
def audio_client() -> TestClient:
    app = FastAPI()
    router = APIRouter(prefix="/knowledge-flow/v1")
    AudioTranscriptionController(router)
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: KeycloakUser(
        uid="test-user",
        username="testuser",
        email="testuser@example.com",
        roles=["admin"],
        groups=["admins"],
    )
    with TestClient(app) as client:
        yield client


def test_transcribe_audio_success(audio_client: TestClient, monkeypatch) -> None:
    captured: dict[str, str | None] = {}

    def _fake_transcribe(self, file_path: Path, language: str | None = None) -> dict[str, object]:
        captured["suffix"] = file_path.suffix
        captured["language"] = language
        captured["content"] = file_path.read_bytes().decode("utf-8")
        return {
            "text": "hello from whisper",
            "lines": ["[00:00:00] hello from whisper"],
            "language": language or "en",
            "duration": 1.2,
        }

    monkeypatch.setattr("knowledge_flow_backend.features.audio.audio_transcription_service.AudioProcessor.transcribe_file_to_text", _fake_transcribe)

    response = audio_client.post(
        "/knowledge-flow/v1/audio/transcriptions",
        files={"file": ("clip.webm", b"fake-audio", "audio/webm")},
        data={"language": "fr"},
    )

    assert response.status_code == 200
    assert response.json() == {"text": "hello from whisper"}
    assert captured == {
        "suffix": ".webm",
        "language": "fr",
        "content": "fake-audio",
    }


def test_transcribe_audio_accepts_codec_parameterized_content_type(audio_client: TestClient, monkeypatch) -> None:
    def _fake_transcribe(self, file_path: Path, language: str | None = None) -> dict[str, object]:
        return {
            "text": "codec ok",
            "lines": ["[00:00:00] codec ok"],
            "language": language or "en",
            "duration": 0.8,
        }

    monkeypatch.setattr("knowledge_flow_backend.features.audio.audio_transcription_service.AudioProcessor.transcribe_file_to_text", _fake_transcribe)

    response = audio_client.post(
        "/knowledge-flow/v1/audio/transcriptions",
        files={"file": ("clip.webm", b"fake-audio", "audio/webm;codecs=opus")},
    )

    assert response.status_code == 200
    assert response.json() == {"text": "codec ok"}


def test_transcribe_audio_rejects_empty_upload(audio_client: TestClient) -> None:
    response = audio_client.post(
        "/knowledge-flow/v1/audio/transcriptions",
        files={"file": ("clip.webm", b"", "audio/webm")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Uploaded audio file is empty."


def test_transcribe_audio_rejects_unsupported_extension(audio_client: TestClient) -> None:
    response = audio_client.post(
        "/knowledge-flow/v1/audio/transcriptions",
        files={"file": ("clip.txt", b"not-audio", "text/plain")},
    )

    assert response.status_code == 400
    assert "Unsupported audio format" in response.json()["detail"]


def test_transcribe_audio_rejects_oversized_upload(audio_client: TestClient) -> None:
    payload = b"a" * (MAX_AUDIO_TRANSCRIPTION_BYTES + 1)

    response = audio_client.post(
        "/knowledge-flow/v1/audio/transcriptions",
        files={"file": ("clip.webm", payload, "audio/webm")},
    )

    assert response.status_code == 400
    assert "Audio file exceeds" in response.json()["detail"]
