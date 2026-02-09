# app/features/reports/service.py (excerpt showing rendering + persist)
from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

from fred_core import KeycloakUser

from knowledge_flow_backend.common.document_structures import (
    DocumentMetadata,
    FileInfo,
    FileType,
    Identity,
    Processing,
    ProcessingStage,
    ProcessingStatus,
    SourceInfo,
    SourceType,
    Tagging,
)
from knowledge_flow_backend.common.report_util import ReportExtensionV1, put_report_extension
from knowledge_flow_backend.features.content.rendering_service import RenderingService


class ReportsService:
    def __init__(self) -> None:
        from knowledge_flow_backend.application_context import ApplicationContext

        ctx = ApplicationContext.get_instance()
        self._content_store = ctx.get_content_store()
        self._metadata_store = ctx.get_metadata_store()
        self._renderer = RenderingService()

    async def write_report(
        self,
        *,
        user: KeycloakUser,
        title: str,
        markdown: str,
        tags: List[str] | None = None,
        template_id: Optional[str] = None,
        render_html: bool = False,
        render_pdf: bool = False,
    ):
        document_uid = str(uuid4())
        now = datetime.now(timezone.utc)

        # 1) Build artifacts (HTML always possible; PDF best-effort)
        html_text = None
        if render_html:
            html_text = self._renderer.markdown_to_html_text(markdown, template_id=template_id)

        pdf_bytes = None
        if render_pdf:
            # If no engine is installed, this will raise NotImplementedError.
            pdf_bytes = self._renderer.markdown_to_pdf_bytes(markdown, template_id=template_id)

        # 2) Persist using your existing layout & API
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            out = root / "output"
            out.mkdir(parents=True, exist_ok=True)

            (out / "output.md").write_text(markdown, encoding="utf-8")
            if html_text is not None:
                (out / "report.html").write_text(html_text, encoding="utf-8")
            if pdf_bytes is not None:
                (out / "report.pdf").write_bytes(pdf_bytes)

            # Ship entire directory; your store will place it under the doc uid
            self._content_store.save_content(document_uid=document_uid, document_dir=root)

        # 3) Metadata (unchanged from previous plan)
        metadata = DocumentMetadata(
            identity=Identity(
                document_uid=document_uid,
                document_name="report.md",
                title=title,
                created=now,
                modified=now,
                last_modified_by=user.username,
            ),
            source=SourceInfo(
                source_type=SourceType.PUSH,
                source_tag="reports",
                retrievable=True,
                pull_location=None,
            ),
            file=FileInfo(file_type=FileType.MD, mime_type="text/markdown"),
            tags=Tagging(tag_names=list(dict.fromkeys(tags or []))),
            processing=Processing(stages={ProcessingStage.PREVIEW_READY: ProcessingStatus.DONE}),
            # Your ContentController /markdown/{uid} will read output/output.md directly.
            # If you add /content/file/{uid}?f=report.html|report.pdf, you can link those too.
        )

        # 4) Store extension URLs pointing to your content endpoints
        # Markdown preview already has a dedicated endpoint:
        base = "/content"  # replace with your app base prefix if needed
        md_url = f"{base}/markdown/{document_uid}"

        html_url = f"{base}/file/{document_uid}?f=report.html" if html_text is not None else None
        pdf_url = f"{base}/file/{document_uid}?f=report.pdf" if pdf_bytes is not None else None

        put_report_extension(
            metadata,
            ReportExtensionV1(
                template_id=template_id,
                md_url=md_url,
                html_url=html_url,
                pdf_url=pdf_url,
                html_type=(FileType.HTML if html_url else None),
                pdf_type=(FileType.PDF if pdf_url else None),
            ),
        )

        await self._metadata_store.save_metadata(metadata)

        return document_uid, md_url, html_url, pdf_url
