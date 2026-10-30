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

"""Library ingestion of Outlook `.msg` and RFC 822 `.eml` mail files."""

from __future__ import annotations

from pathlib import Path

from fred_core.documents.document_structures import DocumentMetadata

from knowledge_flow_backend.core.processors.input.common.base_input_processor import BaseMarkdownProcessor
from knowledge_flow_backend.core.processors.input.email_processor.email_message_parser import (
    EMAIL_SUFFIXES,
    LIBRARY_MAX_BODY_CHARS,
    email_extension,
    email_metadata,
    parse_email_file,
    render_email_markdown,
)


class EmailMarkdownProcessor(BaseMarkdownProcessor):
    description = "Renders .msg and .eml mail files as Markdown: headers, body, attachment names, attached mails and the text of document attachments."

    def check_file_validity(self, file_path: Path) -> bool:
        return file_path.is_file() and file_path.suffix.lower() in EMAIL_SUFFIXES and file_path.stat().st_size > 0

    def extract_file_metadata(self, file_path: Path) -> dict:
        return email_metadata(parse_email_file(file_path))

    def process_metadata(self, file_path: Path, tags: list[str], source_tag: str) -> DocumentMetadata:
        metadata = super().process_metadata(file_path, tags, source_tag)
        # The base enrichment keeps identity fields only, so the recipients are added here.
        metadata.extensions = {**(metadata.extensions or {}), "email": email_extension(parse_email_file(file_path))}
        return metadata

    def convert_file_to_markdown(self, file_path: Path, output_dir: Path, document_uid: str | None) -> dict:
        markdown = render_email_markdown(parse_email_file(file_path), max_body_chars=LIBRARY_MAX_BODY_CHARS)
        output_dir.mkdir(parents=True, exist_ok=True)
        md_path = output_dir / "output.md"
        md_path.write_text(markdown, encoding="utf-8")
        return {"doc_dir": str(output_dir), "md_file": str(md_path)}
