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

from fred_core.common import ModelConfiguration

import knowledge_flow_backend.core.processors.input.common.image_ocr as image_ocr_module
from knowledge_flow_backend.core.processors.input.common.image_ocr import RemoteImageOcr, build_image_ocr


def test_build_image_ocr_returns_none_when_config_missing():
    """
    Ensure OCR adapter construction is optional.

    Why this exists:
    - PDF ingestion must be able to fall back to local OCR when no remote model
      is configured.

    How to use:
    - Call `build_image_ocr(None)` and assert it returns `None`.
    """

    assert build_image_ocr(None) is None


def test_build_image_ocr_uses_shared_model_factory(monkeypatch):
    """
    Ensure the OCR adapter is created from the shared Fred model factory.

    Why this exists:
    - Provider-specific OCR setup should stay centralized in `fred_core`.

    How to use:
    - Patch `get_model`, build the OCR adapter from a `ModelConfiguration`, and
      assert the adapter is constructed.

    Example:
        `ocr = build_image_ocr(ModelConfiguration(provider="openai", name="gpt-4o-mini"))`
    """

    fake_model = SimpleNamespace()

    def fake_get_model(cfg):
        assert cfg.name == "gpt-4o-mini"
        return fake_model

    monkeypatch.setattr(image_ocr_module, "get_model", fake_get_model)

    ocr = build_image_ocr(ModelConfiguration(provider="openai", name="gpt-4o-mini", settings={"temperature": 0}))

    assert isinstance(ocr, RemoteImageOcr)
    assert ocr.model is fake_model


def test_remote_image_ocr_extract_text_normalizes_list_content():
    """
    Ensure OCR results are normalized to plain text across provider payload
    shapes.

    Why this exists:
    - Multimodal providers do not all return a plain string in `result.content`.

    How to use:
    - Feed the OCR adapter a fake model returning list-based content and assert
      the text is flattened.
    """

    captured = {}

    class FakeModel:
        def invoke(self, messages):
            captured["messages"] = messages
            return SimpleNamespace(content=[{"text": "hello"}, {"text": "world"}])

    ocr = RemoteImageOcr(model=FakeModel(), system_prompt="strict prompt", provider="openai")

    text = ocr.extract_text("YWJj")

    assert text == "hello world"
    assert len(captured["messages"]) == 2
    assert captured["messages"][0].content == "strict prompt"
    assert captured["messages"][1].content[1]["image_url"]["url"] == "data:image/png;base64,YWJj"


def test_remote_image_ocr_returns_empty_string_on_error():
    """
    Ensure OCR failures degrade safely without breaking ingestion.

    Why this exists:
    - Remote OCR providers may fail transiently and the processor should handle
      that gracefully.

    How to use:
    - Make the fake model raise and assert the adapter returns an empty string.
    """

    class BrokenModel:
        def invoke(self, messages):
            raise RuntimeError("boom")

    ocr = RemoteImageOcr(model=BrokenModel(), system_prompt="strict prompt", provider="openai")

    assert ocr.extract_text("YWJj") == ""
