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

from pydantic import BaseModel


class FileInfo(BaseModel):
    """
    Minimal metadata about a file stored in a content backend.

    This is the return type of the `put()` method in BaseFileStore, and may be
    used later to retrieve or display file details in logs, UIs, or audits.

    Fields:
        uri (str): Absolute or logical URI of the file. This typically includes:
            - Scheme and path (e.g., `file:///tmp/data/foo.txt`)
            - Or cloud path (e.g., `s3://my-bucket/data/foo.txt`)
            - Or logical format (e.g., `local://templates/cir-summary/v1.md`)
            The URI is primarily for traceability, not guaranteed to be directly fetchable.

        size_bytes (int): Exact number of bytes stored.

        content_type (str): MIME type of the file (e.g., `text/markdown`, `application/json`).
            This is optional in most backends, but helps with preview/rendering logic.

        checksum_sha256 (str): SHA-256 checksum (hex-encoded lowercase string) of the raw content.
            This ensures content integrity and may be used to detect changes or verify uploads.
    """
    uri: str
    size_bytes: int
    content_type: str
    checksum_sha256: str
