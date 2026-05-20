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

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class DocumentGuardrailResult:
    detected_label: str | None
    matched_pattern: str | None
    guardrail_text: str | None
    status: str


class DocumentGuardrailService:
    """
    Minimal ingestion-time guardrail based on explicit document markings.

    Why this exists:
    - Fred should be able to detect visible document markings during ingestion
      without embedding product-specific acceptance policy in processors.
    - The service centralizes regex matching and "no label" behavior.
    """

    def __init__(self, config: Any):
        self.config = config

    def evaluate(self, *, file_path: Path, processor: Any, source_tag: str | None = None) -> DocumentGuardrailResult:
        if not getattr(self.config, "enabled", False):
            return DocumentGuardrailResult(
                detected_label=None,
                matched_pattern=None,
                guardrail_text=None,
                status="disabled",
            )

        source_tags = getattr(self.config, "source_tags", []) or []
        if source_tags and source_tag and source_tag not in source_tags:
            return DocumentGuardrailResult(
                detected_label=None,
                matched_pattern=None,
                guardrail_text=None,
                status="skipped_for_source",
            )

        guardrail_text = processor.extract_guardrail_text(file_path)
        if not guardrail_text:
            return self._handle_no_label(None)

        for pattern_cfg in getattr(self.config, "patterns", []) or []:
            pattern = pattern_cfg.pattern
            label = pattern_cfg.label
            if re.search(pattern, guardrail_text, flags=re.IGNORECASE | re.MULTILINE):
                allowed_labels = getattr(self.config, "allowed_labels", []) or []
                if allowed_labels and label not in allowed_labels:
                    raise ValueError(
                        f"Document rejected: detected label '{label}' is not allowed for ingestion."
                    )
                logger.info(
                    "[GUARDRAIL] Detected document label '%s' for file %s",
                    label,
                    file_path.name,
                )

                return DocumentGuardrailResult(
                    detected_label=label,
                    matched_pattern=pattern,
                    guardrail_text=guardrail_text,
                    status="label_detected",
                )

        return self._handle_no_label(guardrail_text)

    def _handle_no_label(self, guardrail_text: str | None) -> DocumentGuardrailResult:
        mode = getattr(self.config, "on_no_label", "allow")
        
        if mode == "reject":
            raise ValueError("Document rejected: no explicit document marking was detected.")

        if mode == "warn":
            logger.warning("No explicit document marking detected during ingestion guardrail check.")
        
        logger.info("[GUARDRAIL] No explicit document marking detected.")

        return DocumentGuardrailResult(
            detected_label=None,
            matched_pattern=None,
            guardrail_text=guardrail_text,
            status="no_label_detected",
        )
