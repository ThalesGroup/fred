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

"""What a synchronizing caller sends and gets back, and the bounds it must respect.

A source key and a version are the caller's vocabulary: bounded here, never
interpreted. A path is not — it says where in the library the document goes, so
it is checked until nothing but a location inside that library is left.
"""

from __future__ import annotations

from typing import Optional
from urllib.parse import unquote

from pydantic import BaseModel, Field

# A source key is a name, not a document: generous enough for a deep repository
# path, short enough that it cannot be used to store payload in an index.
MAX_SOURCE_KEY_LENGTH = 512
# A version is an etag, a sha or a cursor. Nothing legitimate is longer.
MAX_VERSION_LENGTH = 256
MAX_DOCUMENT_PATH_LENGTH = 1024
MAX_PATH_SEGMENT_LENGTH = 255


class InvalidSourceRequest(Exception):
    """A key, version or path outside what this surface accepts.

    Carries a stable `code` so a caller can branch on the reason without
    matching on prose.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class SynchronizationUnavailable(Exception):
    """This deployment has no scheduler, so it cannot process what it would accept.

    Raised before anything is stored: a write refused whole is one the caller
    retries later; a write half-taken is one it would have to reconcile.
    """


def _reject_control_characters(value: str, *, code: str, label: str) -> None:
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        raise InvalidSourceRequest(code, f"{label} must not contain control characters.")


def validate_source_key(raw: str) -> str:
    """Bound a source key and return it unchanged.

    Deliberately permissive about characters: the key is the caller's own name
    for the document — a repository path, a URI, a record id — and Fred stores
    and matches it verbatim. Only length and control characters are refused,
    and nothing is trimmed: a key that came back different from what was sent
    would silently orphan the document it addressed.
    """
    if not raw or not raw.strip():
        raise InvalidSourceRequest("source_key_empty", "A source key is required.")
    if len(raw) > MAX_SOURCE_KEY_LENGTH:
        raise InvalidSourceRequest(
            "source_key_too_long",
            f"A source key is at most {MAX_SOURCE_KEY_LENGTH} characters.",
        )
    _reject_control_characters(raw, code="source_key_invalid", label="A source key")
    return raw


def validate_version(raw: Optional[str], *, label: str, code_prefix: str) -> Optional[str]:
    """Bound an opaque version and return it unchanged, or None.

    Not parsed, not ordered, not dated — a caller whose source versions look
    like `r7`, `2026-w03` or a base64 cursor is served exactly like one using
    commit shas.
    """
    if raw is None:
        return None
    if not raw.strip():
        raise InvalidSourceRequest(f"{code_prefix}_empty", f"{label} must not be blank.")
    if len(raw) > MAX_VERSION_LENGTH:
        raise InvalidSourceRequest(
            f"{code_prefix}_too_long",
            f"{label} is at most {MAX_VERSION_LENGTH} characters.",
        )
    _reject_control_characters(raw, code=f"{code_prefix}_invalid", label=label)
    return raw


def _reject_escape(candidate: str) -> None:
    """Refuse anything that is not a plain relative location."""
    if candidate.startswith("/"):
        raise InvalidSourceRequest("document_path_absolute", "A document path must be relative to its library.")
    if "\\" in candidate:
        raise InvalidSourceRequest("document_path_invalid", "A document path must use '/' as its only separator.")
    _reject_control_characters(candidate, code="document_path_invalid", label="A document path")
    for segment in candidate.split("/"):
        if not segment:
            raise InvalidSourceRequest("document_path_invalid", "A document path must not contain an empty segment.")
        if segment in (".", ".."):
            raise InvalidSourceRequest("document_path_escapes", "A document path must not leave its library.")


def split_document_path(raw: str) -> tuple[list[str], str]:
    """Split a path within a library into its folders and the document's name.

    Checked twice — as sent, and percent-decoded. The handler receives the form
    field as written, so an encoded traversal arrives literally and would pass a
    check of the raw text alone; decoding first means no later layer can turn an
    accepted path back into an escaping one.
    """
    if not raw or not raw.strip():
        raise InvalidSourceRequest("document_path_empty", "A document path is required.")
    if len(raw) > MAX_DOCUMENT_PATH_LENGTH:
        raise InvalidSourceRequest(
            "document_path_too_long",
            f"A document path is at most {MAX_DOCUMENT_PATH_LENGTH} characters.",
        )

    _reject_escape(raw)
    _reject_escape(unquote(raw))

    segments = raw.split("/")
    for segment in segments:
        if len(segment) > MAX_PATH_SEGMENT_LENGTH:
            raise InvalidSourceRequest(
                "document_path_invalid",
                f"Each path segment is at most {MAX_PATH_SEGMENT_LENGTH} characters.",
            )
    return segments[:-1], segments[-1]


def validate_synchronized_by(raw: str) -> str:
    """Bound the machine reference and return it unchanged.

    Not parsed: Fred acts on its presence, never on what it names. Bounded the
    same way a version is, because it is stored the same way — opaquely.
    """
    bounded = validate_version(raw, label="A machine reference", code_prefix="synchronized_by")
    if bounded is None:
        raise InvalidSourceRequest("synchronized_by_empty", "A machine reference is required.")
    return bounded


class DocumentAccepted(BaseModel):
    """One write taken in: the bytes are stored and the document is queued.

    The key stays the caller's only address for its document. The identifier
    and the task are handles to follow this write to its outcome, not a second
    naming scheme to maintain.
    """

    source_key: str
    path: str
    document_version: Optional[str] = None
    created: bool = Field(
        ...,
        description="True when this key was new to the library, False when it updated the document already there.",
    )
    document_uid: str = Field(..., description="Fred's identifier for the document this key now names.")
    task_id: str = Field(..., description="The task processing this write; follow it for the outcome.")


class DocumentRemoved(BaseModel):
    source_key: str
    removed: bool = Field(
        ...,
        description="False when the library did not hold that key — not an error: a source that removes twice is still in sync.",
    )


class LibrarySourceVersion(BaseModel):
    """The version of its own source a library last accepted; null if never."""

    source_version: Optional[str] = None


class LibrarySynchronizedBy(BaseModel):
    """Which machine fills a library, as `<kind>:<id>`."""

    synchronized_by: str = Field(
        ...,
        description=('Qualified reference to the machine that fills this library, e.g. "knowledge_base:ab12". Opaque to Fred: only its presence is acted on.'),
    )
