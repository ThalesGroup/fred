# app/features/reports/controller.py
# Copyright Thales 2025
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fred_core import KeycloakUser, get_current_user
from pydantic import BaseModel, Field
from typing import List, Optional

from app.common.utils import log_exception
from app.features.content.report_service import ReportsService

# --- Module-level router, same pattern as Agents controller ---
router = APIRouter(tags=["Reports"])


# --- I/O models kept tiny and explicit ---


class WriteReportRequest(BaseModel):
    title: str = Field(..., description="Report title shown in UI")
    markdown: str = Field(..., description="Canonical Markdown content (stored as-is)")
    template_id: Optional[str] = Field(default=None, description="Optional template identifier for traceability")
    tags: List[str] = Field(default_factory=list, description="UI tags (chips)")
    # Allowed values: "md", "html", "pdf". MD is always produced.
    render_formats: List[str] = Field(default_factory=lambda: ["md"])


class WriteReportResponse(BaseModel):
    document_uid: str
    md_url: str
    html_url: Optional[str] = None
    pdf_url: Optional[str] = None


def handle_exception(e: Exception) -> HTTPException | Exception:
    # Keep this open for future domain errors (e.g., RendererUnavailable)
    return HTTPException(status_code=500, detail=str(e))


@router.post(
    "/mcp/reports/write",
    summary="Create a simple report (Markdown canonical) and return URLs",
    response_model=WriteReportResponse,
)
async def write_report(
    req: WriteReportRequest,
    user: KeycloakUser = Depends(get_current_user),
):
    """
    Fred rationale:
    - Controllers stay skinny; all logic is inside ReportsService.
    - Markdown is canonical; HTML/PDF are optional synchronous exports.
    - Everything lands under source_tag='reports' and MinIO prefix 'reports/'.
    """
    try:
        service = ReportsService()  # self-wired; no ApplicationContext in the controller
        wants_html = "html" in req.render_formats
        wants_pdf = "pdf" in req.render_formats

        doc_uid, md_url, html_url, pdf_url = await service.write_report(
            user=user,
            title=req.title,
            markdown=req.markdown,
            tags=req.tags,
            template_id=req.template_id,
            render_html=wants_html,
            render_pdf=wants_pdf,
        )
        return WriteReportResponse(
            document_uid=doc_uid,
            md_url=md_url,
            html_url=html_url,
            pdf_url=pdf_url,
        )
    except Exception as e:
        log_exception(e)
        raise handle_exception(e)
