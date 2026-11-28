# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

import pytest

from knowledge_flow_worker.core.processors.input.audio_processor import audio_processor


@pytest.fixture(autouse=True)
def _fresh_whisper_cache():
    """Each test loads its own fake model instead of one a previous test cached."""
    audio_processor._MODELS.clear()
    yield
    audio_processor._MODELS.clear()
