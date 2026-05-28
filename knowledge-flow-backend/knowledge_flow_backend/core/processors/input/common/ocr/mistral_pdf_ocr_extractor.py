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

import os
from pathlib import Path
from typing import Any, Dict

import httpx
from fred_core.common import ModelConfiguration

from knowledge_flow_backend.core.processors.input.common.ocr.base_pdf_ocr_extractor import (
    BasePdfOcrExtractor,
    RemotePdfOcrImage,
    RemotePdfOcrPage,
    RemotePdfOcrResult,
)


def _resolve_timeout(settings: Dict[str, Any]) -> httpx.Timeout:
    request_timeout = settings.get("request_timeout")
    if isinstance(request_timeout, (int, float)):
        return httpx.Timeout(float(request_timeout))

    timeout_cfg = settings.get("timeout")
    if isinstance(timeout_cfg, dict):
        connect = float(timeout_cfg.get("connect", 10.0))
        read = float(timeout_cfg.get("read", 300.0))
        write = float(timeout_cfg.get("write", read))
        pool = float(timeout_cfg.get("pool", connect))
        return httpx.Timeout(connect=connect, read=read, write=write, pool=pool)

    return httpx.Timeout(300.0)


class MistralPdfOcrExtractor(BasePdfOcrExtractor):
    """
    Why:
        Support Mistral's native OCR API for PDF ingestion so constrained
        Kubernetes workers can offload OCR CPU and memory costs to the remote
        model service.

    How to use:
        Configure `ocr_model` with `name: mistral-ocr-latest` (or another
        Mistral OCR model), plus `settings.base_url`. Call
        `extract_pdf_markdown(...)` with a local PDF path.

    Example:
        `extractor = MistralPdfOcrExtractor(cfg)`
        `result = extractor.extract_pdf_result(Path("/tmp/report.pdf"), include_images=True)`
    """

    def __init__(self, ocr_cfg: ModelConfiguration) -> None:
        self.ocr_cfg = ocr_cfg
        self.settings: Dict[str, Any] = dict(ocr_cfg.settings or {})
        self.base_url = str(self.settings.get("base_url") or "https://api.mistral.ai/v1").rstrip("/")
        self.timeout = _resolve_timeout(self.settings)
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(f"Missing OPENAI_API_KEY for remote OCR model '{ocr_cfg.name}'.")
        self.signed_url_expiry_hours = int(self.settings.get("signed_url_expiry_hours") or 1)
        self.include_image_base64 = bool(self.settings.get("include_image_base64") or False)

    def extract_pdf_result(self, file_path: Path, *, include_images: bool = False) -> RemotePdfOcrResult:
        """
        Why:
            Upload one PDF to Mistral's Files API, obtain a short-lived signed
            URL, and submit it to the OCR endpoint to receive per-page
            markdown and optional per-image payloads.

        How to use:
            Pass one local PDF path. Set `include_images=True` when the caller
            plans to enrich OCR image references with a vision model.

        Example:
            `result = extractor.extract_pdf_result(Path("/tmp/report.pdf"), include_images=True)`
        """
        with httpx.Client(
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=self.timeout,
        ) as client:
            file_id = self._upload_pdf(client, file_path)
            signed_url = self._get_signed_url(client, file_id)
            response = self._process_document(client, signed_url, include_images=include_images)

        pages = response.get("pages")
        if not isinstance(pages, list):
            raise ValueError("Mistral OCR response did not include a 'pages' array.")

        ocr_pages: list[RemotePdfOcrPage] = []
        for page in pages:
            if not isinstance(page, dict):
                continue
            markdown = page.get("markdown")
            if not isinstance(markdown, str) or not markdown.strip():
                continue
            images = self._extract_page_images(page)
            ocr_pages.append(RemotePdfOcrPage(markdown=markdown.strip(), images=images))

        result = RemotePdfOcrResult(pages=ocr_pages)
        markdown = result.to_markdown()
        if not markdown:
            raise ValueError("Mistral OCR returned no markdown content.")
        return result

    def _upload_pdf(self, client: httpx.Client, file_path: Path) -> str:
        response = client.post(
            f"{self.base_url}/files",
            data={"purpose": "ocr"},
            files={"file": (file_path.name, file_path.read_bytes(), "application/pdf")},
        )
        response.raise_for_status()
        payload = response.json()
        file_id = payload.get("id")
        if not isinstance(file_id, str) or not file_id:
            raise ValueError("Mistral file upload response did not include a valid file id.")
        return file_id

    def _get_signed_url(self, client: httpx.Client, file_id: str) -> str:
        response = client.get(
            f"{self.base_url}/files/{file_id}/url",
            params={"expiry": self.signed_url_expiry_hours},
        )
        response.raise_for_status()
        payload = response.json()
        signed_url = payload.get("url")
        if not isinstance(signed_url, str) or not signed_url:
            raise ValueError("Mistral signed-url response did not include a valid URL.")
        return signed_url

    def _extract_page_images(self, page_payload: Dict[str, Any]) -> list[RemotePdfOcrImage]:
        """
        Why:
            Normalize Mistral's page image payload into the provider-agnostic
            OCR image container used by Fred's remote OCR post-processing.

        How to use:
            Pass one `pages[]` JSON object from the OCR response. The helper
            keeps only images that expose both an identifier and base64 data.

        Example:
            `images = self._extract_page_images(page_payload)`
        """
        raw_images = page_payload.get("images")
        if not isinstance(raw_images, list):
            return []

        images: list[RemotePdfOcrImage] = []
        for image_payload in raw_images:
            if not isinstance(image_payload, dict):
                continue
            image_id = image_payload.get("id") or image_payload.get("image_id") or image_payload.get("name")
            image_base64 = image_payload.get("image_base64") or image_payload.get("base64")
            if not isinstance(image_id, str) or not image_id:
                continue
            if not isinstance(image_base64, str) or not image_base64:
                continue
            images.append(RemotePdfOcrImage(image_id=image_id, image_base64=image_base64))
        return images

    def _process_document(self, client: httpx.Client, signed_url: str, *, include_images: bool) -> Dict[str, Any]:
        """
        Why:
            Submit the uploaded PDF to Mistral OCR with the exact image payload
            level required by the caller.

        How to use:
            Pass an authenticated client, the signed document URL, and whether
            the OCR response should include base64 page images.

        Example:
            `payload = self._process_document(client, signed_url, include_images=True)`
        """
        response = client.post(
            f"{self.base_url}/ocr",
            json={
                "model": self.ocr_cfg.name,
                "document": {
                    "type": "document_url",
                    "document_url": signed_url,
                },
                "include_image_base64": include_images or self.include_image_base64,
            },
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Mistral OCR response payload must be a JSON object.")
        return payload
