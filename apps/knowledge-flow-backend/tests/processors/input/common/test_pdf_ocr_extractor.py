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

from pathlib import Path

import pytest
from fred_core.common import ModelConfiguration

from knowledge_flow_backend.core.processors.input.common.ocr.base_pdf_ocr_extractor import (
    BasePdfOcrExtractor,
    RemotePdfOcrResult,
)
from knowledge_flow_backend.core.processors.input.common.ocr.mistral_pdf_ocr_extractor import (
    MistralPdfOcrExtractor,
)
from knowledge_flow_backend.core.processors.input.common.ocr.pdf_ocr_factory import (
    build_pdf_ocr_extractor,
)


def test_build_pdf_ocr_extractor_returns_none_without_configuration():
    assert build_pdf_ocr_extractor(None) is None


def test_build_pdf_ocr_extractor_recognizes_mistral_ocr():
    extractor = build_pdf_ocr_extractor(
        ModelConfiguration(
            provider="openai",
            name="mistral-ocr-latest",
            settings={"base_url": "https://api.mistral.ai/v1"},
        )
    )

    assert isinstance(extractor, MistralPdfOcrExtractor)
    assert isinstance(extractor, BasePdfOcrExtractor)


@pytest.mark.parametrize(
    ("dedicated_key", "expected_key"),
    [("ocr-key", "ocr-key"), (" ", "test-key"), (None, "test-key")],
)
def test_mistral_pdf_ocr_extractor_concatenates_page_markdown(monkeypatch, tmp_path: Path, dedicated_key: str | None, expected_key: str):
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    if dedicated_key is None:
        monkeypatch.delenv("KNOWLEDGE_FLOW_OCR_API_KEY", raising=False)
    else:
        monkeypatch.setenv("KNOWLEDGE_FLOW_OCR_API_KEY", dedicated_key)

    requests: list[tuple[str, str, object, object]] = []
    headers: list[dict[str, str]] = []

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self, *args, **kwargs):
            headers.append(kwargs["headers"])

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def post(self, url, data=None, files=None, json=None):
            requests.append(("POST", url, data if data is not None else json, files))
            if url.endswith("/files"):
                return FakeResponse({"id": "file-123"})
            if url.endswith("/ocr"):
                return FakeResponse(
                    {
                        "pages": [
                            {"markdown": "# Page 1"},
                            {"markdown": "Second page"},
                        ]
                    }
                )
            raise AssertionError(f"Unexpected POST url {url}")

        def get(self, url, params=None):
            requests.append(("GET", url, params, None))
            if url.endswith("/files/file-123/url"):
                return FakeResponse({"url": "https://signed.example/doc.pdf"})
            raise AssertionError(f"Unexpected GET url {url}")

    monkeypatch.setattr(
        "knowledge_flow_backend.core.processors.input.common.ocr.mistral_pdf_ocr_extractor.httpx.Client",
        FakeClient,
    )

    extractor = MistralPdfOcrExtractor(
        ModelConfiguration(
            provider="openai",
            name="mistral-ocr-latest",
            settings={"base_url": "https://api.mistral.ai/v1"},
        )
    )

    result = extractor.extract_pdf_result(pdf_path, include_images=True)
    markdown = result.to_markdown()

    assert markdown == "# Page 1\n\nSecond page"
    assert isinstance(result, RemotePdfOcrResult)
    assert requests[0][1] == "https://api.mistral.ai/v1/files"
    assert requests[1][1] == "https://api.mistral.ai/v1/files/file-123/url"
    assert requests[2][1] == "https://api.mistral.ai/v1/ocr"
    assert requests[2][2]["include_image_base64"] is True
    assert headers == [{"Authorization": f"Bearer {expected_key}"}]


def test_mistral_pdf_ocr_extractor_requires_key_before_request(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("KNOWLEDGE_FLOW_OCR_API_KEY", raising=False)

    with pytest.raises(ValueError, match="KNOWLEDGE_FLOW_OCR_API_KEY"):
        MistralPdfOcrExtractor(ModelConfiguration(provider="openai", name="mistral-ocr-latest"))


def test_mistral_pdf_ocr_extractor_keeps_name_based_provider_selection(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "fallback-key")
    monkeypatch.delenv("KNOWLEDGE_FLOW_OCR_API_KEY", raising=False)

    extractor = MistralPdfOcrExtractor(ModelConfiguration(provider="mistral", name="mistral-ocr-latest"))

    assert extractor.api_key == "fallback-key"  # pragma: allowlist secret
