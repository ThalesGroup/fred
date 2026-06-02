# Copyright Thales 2025
# SPDX-License-Identifier: Apache-2.0

"""
RenderingService (pypandoc-based)

Fred rationale:
- Markdown is the source of truth; HTML/PDF are optional exports.
- HTML must always work (no extra deps). PDF is best-effort: we auto-pick a
  pdf-engine if present; otherwise we raise a clear NotImplementedError.
"""

from __future__ import annotations

import shutil
from typing import Iterable, Optional

import pypandoc


def _pandoc_args_html(template_id: Optional[str]) -> list[str]:
    """
    Reasonable defaults:
    - gfm flavor for tables/fences; html5 standalone page
    - no styling here; your UI can style if it inlines HTML
    """
    args = [
        "--from=markdown+gfm",
        "--to=html5",
        "--standalone",
    ]
    # If you later map template_id -> template path, add: args += ["--template", tpl_path]
    return args


def _detect_pdf_engine() -> Optional[str]:
    """
    Try engines in a pragmatic order. We don't bundle these; we detect them.
    Any one is fine.
    """
    candidates = [
        "wkhtmltopdf",
        "weasyprint",  # Pandoc supports it via --pdf-engine=weasyprint
        "tectonic",
        "xelatex",
        "pdflatex",
    ]
    for name in candidates:
        if shutil.which(name):
            return name
    return None


def _pandoc_args_pdf(template_id: Optional[str], engine: str) -> list[str]:
    args = [
        "--from=markdown+gfm",
        "--to=pdf",
        f"--pdf-engine={engine}",
        "--standalone",
    ]
    # If you later map template_id -> CSS/filters/reference-doc, add them here
    return args


class RenderingService:
    """Tiny adapter around pypandoc with safe defaults and clear failure modes."""

    def markdown_to_html_text(self, markdown: str, template_id: Optional[str] = None) -> str:
        """
        Convert Markdown to a standalone HTML5 document. Always available.
        """
        return pypandoc.convert_text(markdown, to="html5", format="md", extra_args=_pandoc_args_html(template_id))

    def markdown_to_pdf_bytes(
        self,
        markdown: str,
        template_id: Optional[str] = None,
        preferred_engines: Optional[Iterable[str]] = None,
    ) -> bytes:
        """
        Convert Markdown to PDF bytes.
        - We auto-detect a pdf engine (wkhtmltopdf/weasyprint/tectonic/xelatex/pdflatex).
        - If none is present, we raise NotImplementedError with a helpful message.
        """
        engine = None
        # Prefer caller's engine choice if present & installed
        if preferred_engines:
            for name in preferred_engines:
                if shutil.which(name):
                    engine = name
                    break
        # Otherwise auto-detect
        engine = engine or _detect_pdf_engine()
        if not engine:
            raise NotImplementedError("PDF rendering requires a pdf engine (wkhtmltopdf, weasyprint, tectonic, xelatex, or pdflatex). Install one, or skip PDF for now.")

        pdf_bytes = pypandoc.convert_text(
            markdown,
            to="pdf",
            format="md",
            extra_args=_pandoc_args_pdf(template_id, engine),
            outputfile=None,  # return bytes
        )
        # pypandoc returns bytes when outputfile=None and to='pdf'
        return pdf_bytes  # type: ignore[return-value]
