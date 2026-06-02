# app/features/reports/utils.py
from typing import Any, Dict, Optional

from knowledge_flow_backend.common.document_structures import DocumentMetadata, ReportExtensionV1

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
