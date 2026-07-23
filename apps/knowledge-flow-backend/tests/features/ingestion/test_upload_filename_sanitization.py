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

"""Client-supplied upload filenames must never reach a filesystem path raw.

Browsers upload a file picked out of a folder (a `webkitdirectory` input or a
dropped directory) under its RELATIVE path as the multipart filename — writing
`<tmp>/input/<that>` then fails on the missing subdirectories, surfacing to the
user as an opaque 404 per file (found live 2026-07-23 dropping a nested folder
on a corpus library). A hostile client can likewise send `../` segments. These
tests pin the sanitization: only the leaf name is ever used on disk.
"""

from __future__ import annotations

import io

from fastapi import UploadFile

from knowledge_flow_backend.features.ingestion.ingestion_controller import (
    cleanup_uploaded_temp_file,
    upload_basename,
    uploadfile_to_path,
)


class TestUploadBasename:
    def test_keeps_a_plain_name(self):
        assert upload_basename("report.pdf") == "report.pdf"

    def test_strips_a_relative_folder_path(self):
        assert upload_basename("data/sub/report.pdf") == "report.pdf"

    def test_strips_windows_separators(self):
        assert upload_basename("data\\sub\\report.pdf") == "report.pdf"

    def test_neutralizes_traversal_segments(self):
        assert upload_basename("../../etc/passwd") == "passwd"
        assert upload_basename("..") == "uploaded_file"

    def test_falls_back_on_empty_or_degenerate_names(self):
        assert upload_basename(None) == "uploaded_file"
        assert upload_basename("") == "uploaded_file"
        assert upload_basename("data/sub/") == "uploaded_file"


class TestUploadfileToPath:
    def test_writes_folder_originated_upload_under_its_leaf_name(self):
        upload = UploadFile(file=io.BytesIO(b"col\n1\n"), filename="data/sub/report.csv")
        path = uploadfile_to_path(upload)
        try:
            assert path.name == "report.csv"
            assert path.parent.name == "input"
            assert path.read_bytes() == b"col\n1\n"
        finally:
            cleanup_uploaded_temp_file(path)
