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

import io
import json
import logging
from datetime import datetime, timezone
from typing import List, Sequence, override

from knowledge_flow_backend.application_context import ApplicationContext
from fred_core.processors import DocumentMetadata, LibraryDocumentInput, LibraryOutputProcessor

logger = logging.getLogger(__name__)


class LibraryTocOutputProcessor(LibraryOutputProcessor):
    """
    Lightweight library-level processor that produces a summary/TOC.

    - Aggregates simple stats per document (chars, words).
    - Stores a summary JSON in the content store under a library namespace.
    - Adds a `library_toc` extension to each document's metadata.
    """

    description = "Aggregates library-level stats and publishes a TOC summary JSON for each collection."

    def __init__(self) -> None:
        self.context = ApplicationContext.get_instance()
        self.content_store = self.context.get_content_store()

    @override
    def process_library(
        self,
        documents: Sequence[LibraryDocumentInput],
        library_tag: str | None = None,
    ) -> List[DocumentMetadata]:
        if not documents:
            return []

        summary_items = []
        updated_metadata: List[DocumentMetadata] = []

        for entry in documents:
            try:
                with open(entry.file_path, "r", encoding="utf-8") as f:
                    text = f.read()
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "LibraryTocOutputProcessor: failed to read %s (%s)",
                    entry.file_path,
                    exc,
                )
                text = ""

            char_count = len(text)
            word_count = len(text.split()) if text else 0

            summary_items.append(
                {
                    "document_uid": entry.metadata.document_uid,
                    "document_name": entry.metadata.document_name,
                    "char_count": char_count,
                    "word_count": word_count,
                }
            )

            updated_metadata.append(entry.metadata)

        summary = {
            "library_tag": library_tag,
            "document_count": len(summary_items),
            "generated_at": datetime.now(tz=timezone.utc).isoformat(),
            "documents": summary_items,
        }

        prefix = f"library/{library_tag or 'default'}"
        key = f"{prefix}/toc-summary.json"

        try:
            payload = json.dumps(summary, ensure_ascii=True, indent=2).encode("utf-8")
            stream = io.BytesIO(payload)
            self.content_store.put_object(
                key=key,
                stream=stream,
                content_type="application/json",
            )
            logger.info("LibraryTocOutputProcessor: stored summary at %s", key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("LibraryTocOutputProcessor: failed to store summary at %s (%s)", key, exc)

        bundle_meta = {
            "bundle_key": key,
            "library_tag": library_tag,
            "document_count": len(summary_items),
        }

        for meta in updated_metadata:
            meta.extensions = meta.extensions or {}
            meta.extensions["library_toc"] = bundle_meta

        return updated_metadata
