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

"""Open user ``.pptx`` bytes without a zip bomb. python-pptx decompresses every
member up front and the upload limit bounds only the compressed size, so the
declared sizes are checked first (zipfile never inflates past them)."""

from __future__ import annotations

import io
import zipfile

from pptx import Presentation
from pptx.presentation import Presentation as PresentationType

MAX_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
MAX_MEMBER_BYTES = 256 * 1024 * 1024
# Above this size a member must not inflate more than MAX_RATIO times: a large
# slide XML compresses ~10-30x, a bomb thousands of times.
RATIO_CHECKED_BYTES = 10 * 1024 * 1024
MAX_RATIO = 100


class UnsafeArchiveError(ValueError):
    """The archive would inflate beyond what a template may hold."""


def check_archive(content: bytes) -> None:
    """Raise :class:`UnsafeArchiveError` before anything is decompressed."""
    try:
        members = zipfile.ZipFile(io.BytesIO(content)).infolist()
    except zipfile.BadZipFile:
        return  # python-pptx reports an unreadable file itself
    total = 0
    for member in members:
        size = member.file_size
        total += size
        if size > MAX_MEMBER_BYTES or total > MAX_UNCOMPRESSED_BYTES:
            raise UnsafeArchiveError(
                "The file inflates to more than a presentation template may hold."
            )
        if size > RATIO_CHECKED_BYTES and size > MAX_RATIO * max(
            member.compress_size, 1
        ):
            raise UnsafeArchiveError(
                f"The file holds an abnormally compressed part ({member.filename})."
            )


def open_presentation(content: bytes) -> PresentationType:
    """``Presentation`` of user bytes, the archive checked first (CPU-bound)."""
    check_archive(content)
    return Presentation(io.BytesIO(content))
