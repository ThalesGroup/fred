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

# app/features/reports/utils.py
from typing import Any, Dict, Optional

from fred_core.documents.document_structures import DocumentMetadata, ReportExtensionV1

REPORT_EXT_KEY = "report"  # single, stable namespace key


def put_report_extension(meta: DocumentMetadata, ext: ReportExtensionV1) -> None:
    """
    Fred rationale:
    - Always write typed data under a reserved key.
    - Never leak untyped dicts into call-sites.
    """
    base: Dict[str, Any] = meta.extensions or {}
    base[REPORT_EXT_KEY] = ext.model_dump()
    meta.extensions = base  # persist as plain JSON in metadata store


def get_report_extension(meta: DocumentMetadata) -> Optional[ReportExtensionV1]:
    """
    Return a typed view of the report extension, or None.
    Safe for non-report documents (extensions may be absent).
    """
    if not meta.extensions:
        return None
    raw = meta.extensions.get(REPORT_EXT_KEY)
    if not raw:
        return None
    return ReportExtensionV1.model_validate(raw)
