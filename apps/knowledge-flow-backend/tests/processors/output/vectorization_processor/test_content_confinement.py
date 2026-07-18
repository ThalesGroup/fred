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

"""No document-content fragments in the generic app-log store (issue #2009).

`SemanticSplitter`'s anchoring loop used to log raw chunk/window text previews
at DEBUG level; those lines reach the generic, now-durable app-log store (see
docs/swift/platform/OBSERVABILITY-AND-AUDIT.md §7 — content must appear in
no observability stream). This locks in that the fix holds regardless of how
the anchoring logic is refactored later.
"""

from __future__ import annotations

import inspect
import logging

from knowledge_flow_backend.core.processors.output.vectorization_processor import (
    semantic_splitter as semantic_splitter_module,
    vectorization_processor as vectorization_processor_module,
)
from knowledge_flow_backend.core.processors.output.vectorization_processor.semantic_splitter import (
    SemanticSplitter,
)

SECRET_MARKER = "SUPER-SECRET-DOCUMENT-CONTENT-MARKER-42"


def test_semantic_chunking_never_logs_document_content(caplog) -> None:
    text = "\n\n".join([f"## Section {i}\n{SECRET_MARKER} paragraph {i} " + ("lorem ipsum " * 40) for i in range(6)])

    splitter = SemanticSplitter(chunk_size=200, chunk_overlap=20)
    with caplog.at_level(logging.DEBUG, logger=semantic_splitter_module.__name__):
        chunks = splitter.semantic_chunking(text)

    assert chunks, "sanity: the splitter actually produced chunks"
    for record in caplog.records:
        assert SECRET_MARKER not in record.getMessage(), f"document content leaked into a log record: {record.getMessage()!r}"


def test_vectorization_processor_chunk_logging_never_slices_page_content() -> None:
    """Static guard: the two chunk-logging call sites must never pass a raw
    text slice of `doc.page_content` (the exact shape of the original leak,
    `doc.page_content[:100]`) — only `len(doc.page_content)` is allowed.
    """
    source = inspect.getsource(vectorization_processor_module)
    assert "page_content[:" not in source
    assert "page_content[0:" not in source
