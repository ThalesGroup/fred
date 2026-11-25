# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

from io import BytesIO
from types import SimpleNamespace
from wave import open as wave_open

import numpy as np
import pytest
from aiohttp import FormData
from aiohttp.test_utils import TestClient, TestServer

from knowledge_flow_worker import dictation
from knowledge_flow_worker.core.processors.input.audio_processor.audio_processor import AudioProcessor


def recording(seconds: int) -> FormData:
    buffer = BytesIO()
    with wave_open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(bytes(8000 * 2 * seconds))
    form = FormData()
    form.add_field("model", "whisper")
    form.add_field("file", buffer.getvalue(), filename="recording.wav", content_type="audio/wav")
    return form


@pytest.mark.asyncio
@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_local_dictation_authenticates_and_bounds_audio_before_inference(monkeypatch: pytest.MonkeyPatch):
    converted = []

    def transcribe(audio: np.ndarray, **_):
        assert audio.dtype == np.float32 and audio.shape == (16000,)
        converted.append(audio.size)
        return [SimpleNamespace(text=" Salut ! ", start=0)], SimpleNamespace(language="fr", duration=1)

    monkeypatch.setattr(AudioProcessor, "_get_model", lambda _: SimpleNamespace(transcribe=transcribe))
    monkeypatch.setattr(dictation, "MAX_SECONDS", 1)
    async with TestClient(TestServer(dictation.create_app("test-worker-key"))) as client:
        path = "/v1/audio/transcriptions"
        async with client.post(path, data=recording(1)) as reply:
            assert reply.status == 401
        headers = {"Authorization": "Bearer test-worker-key"}
        async with client.post(path, headers=headers, data=recording(2)) as reply:
            assert reply.status == 400, await reply.text()
        assert not converted
        async with client.post(path, headers=headers, data=recording(1)) as reply:
            assert reply.status == 200, await reply.text()
            assert await reply.json() == {"text": "Salut !"}
    assert converted == [16000]
