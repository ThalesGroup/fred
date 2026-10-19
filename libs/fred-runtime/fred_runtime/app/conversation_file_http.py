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
"""Bounded HTTP encoding for already-authorized conversation text files."""

from __future__ import annotations

import json
from collections.abc import Iterator

from fastapi.responses import StreamingResponse
from fred_sdk.contracts.context import ConversationFileResponse
from pydantic import TypeAdapter

_TEXT_CHUNK_SIZE = 1024 * 1024
_TEXT_JSON = TypeAdapter(str)


def _text_chunks(content: str) -> Iterator[str]:
    for offset in range(0, len(content), _TEXT_CHUNK_SIZE):
        yield content[offset : offset + _TEXT_CHUNK_SIZE]


def utf8_text_chunks(content: str) -> Iterator[bytes]:
    """Encode Markdown in the response iterator's worker, without a full-file copy."""
    for piece in _text_chunks(content):
        yield piece.encode("utf-8")


def conversation_file_json_response(
    file: ConversationFileResponse,
) -> StreamingResponse:
    # Callers supply a validated model before headers are sent. Starlette runs
    # this synchronous iterator off-loop; each JSON escape operation stays bounded.
    def chunks() -> Iterator[bytes]:
        metadata = json.dumps(file.model_dump(exclude={"content"}), ensure_ascii=True)
        yield (metadata[:-1] + ',"content":"').encode("ascii")
        for piece in _text_chunks(file.content):
            yield _TEXT_JSON.dump_json(piece)[1:-1]
        yield b'"}'

    return StreamingResponse(chunks(), media_type="application/json")
