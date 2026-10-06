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

"""Upload validation shared by team avatars and user profile pictures."""

from __future__ import annotations

from pathlib import Path

from fastapi import UploadFile

MAX_AVATAR_FILE_SIZE_BYTES = 5 * 1024 * 1024
_ALLOWED_AVATAR_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
_AVATAR_EXTENSION_BY_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


class AvatarUploadError(Exception):
    """Raised when avatar upload validation fails (mapped to HTTP 400)."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def _detect_image_content_type(payload: bytes) -> str | None:
    if payload.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(payload) >= 12 and payload[0:4] == b"RIFF" and payload[8:12] == b"WEBP":
        return "image/webp"
    return None


async def read_avatar_upload(file: UploadFile) -> tuple[bytes, str, str]:
    """Read and validate an avatar upload; return `(payload, content_type, extension)`.

    The declared type must be JPEG/PNG/WebP and match the file's magic bytes.
    Raises `AvatarUploadError` otherwise. The caller still owns `file.close()`.
    """
    payload = await file.read(MAX_AVATAR_FILE_SIZE_BYTES + 1)
    if len(payload) > MAX_AVATAR_FILE_SIZE_BYTES:
        raise AvatarUploadError(
            f"File too large: {len(payload)} bytes (max: {MAX_AVATAR_FILE_SIZE_BYTES})"
        )
    if not payload:
        raise AvatarUploadError("Empty file upload is not allowed")

    declared_content_type = (file.content_type or "application/octet-stream").lower()
    if declared_content_type not in _ALLOWED_AVATAR_MIME_TYPES:
        raise AvatarUploadError(f"Invalid content type: {declared_content_type}")

    detected_content_type = _detect_image_content_type(payload)
    if detected_content_type not in _ALLOWED_AVATAR_MIME_TYPES:
        raise AvatarUploadError(
            f"File content doesn't match allowed image formats: {detected_content_type or 'unknown'}"
        )
    if detected_content_type != declared_content_type:
        raise AvatarUploadError(
            f"File content doesn't match declared content type: {detected_content_type}"
        )

    extension = Path(file.filename or "").suffix.lower()
    if not extension:
        extension = _AVATAR_EXTENSION_BY_MIME[detected_content_type]
    return payload, detected_content_type, extension
