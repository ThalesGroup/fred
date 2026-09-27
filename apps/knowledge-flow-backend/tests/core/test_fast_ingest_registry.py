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

from knowledge_flow_backend.core.processors.input.fast_text_processor.fast_lite_doc_processor import FastLiteDocProcessor
from knowledge_flow_backend.core.processors.input.fast_text_processor.fast_lite_odt_processor import FastLiteOdtProcessor
from knowledge_flow_backend.core.processors.input.fast_text_processor.fast_lite_ppt_processor import FastLitePptProcessor
from knowledge_flow_backend.features.ingestion.ingestion_controller import IngestionController


def test_fast_ingest_default_registry_covers_supported_attachment_types() -> None:
    controller = object.__new__(IngestionController)

    registry = controller._build_fast_text_registry()

    for ext in [
        ".pdf",
        ".docx",
        ".doc",
        ".odt",
        ".pptx",
        ".ppt",
        ".csv",
        ".txt",
        ".md",
        ".xlsx",
        ".xls",
        ".xlsm",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".bmp",
        ".svg",
        ".webp",
        ".ico",
    ]:
        assert ext in registry, f"missing fast-ingest processor for {ext}"


def test_fast_ingest_default_registry_maps_legacy_office_formats() -> None:
    """Legacy .doc/.ppt attachments must route to their LibreOffice-backed fast processors."""
    controller = object.__new__(IngestionController)

    registry = controller._build_fast_text_registry()

    assert registry[".doc"] is FastLiteDocProcessor
    assert registry[".ppt"] is FastLitePptProcessor
    assert registry[".odt"] is FastLiteOdtProcessor
