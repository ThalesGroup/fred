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

import logging
from typing import Optional

from fred_core.common import ModelConfiguration

from knowledge_flow_backend.core.processors.input.common.ocr.base_pdf_ocr_extractor import (
    BasePdfOcrExtractor,
)
from knowledge_flow_backend.core.processors.input.common.ocr.mistral_pdf_ocr_extractor import (
    MistralPdfOcrExtractor,
)

logger = logging.getLogger(__name__)


def build_pdf_ocr_extractor(ocr_cfg: Optional[ModelConfiguration]) -> Optional[BasePdfOcrExtractor]:
    """
    Why:
        Keep OCR extractor selection centralized and let callers fall back to
        local OCR automatically when no remote OCR backend is configured.

    How to use:
        Pass the optional `ocr_model` configuration. The function returns a
        concrete extractor when the model is supported, otherwise `None`.

    Example:
        `extractor = build_pdf_ocr_extractor(configuration.ocr_model)`
    """
    if not ocr_cfg:
        return None
    if isinstance(ocr_cfg.name, str) and ocr_cfg.name.lower().startswith("mistral-ocr"):
        return MistralPdfOcrExtractor(ocr_cfg)

    logger.warning(
        "[PROCESSOR][PDF][OCR] Unsupported remote OCR model provider=%s name=%s; falling back to local Docling OCR.",
        ocr_cfg.provider,
        ocr_cfg.name,
    )
    return None
