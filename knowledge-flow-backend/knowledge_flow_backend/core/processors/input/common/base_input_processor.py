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

import hashlib
import logging
import mimetypes
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Optional

import pandas  # kept because BaseTabularProcessor references it

from knowledge_flow_backend.common.document_structures import (
    DocumentMetadata,
    FileInfo,
    FileType,
    Identity,
    SourceInfo,
    SourceType,
    Tagging,
)
from knowledge_flow_backend.common.source_utils import resolve_source_type
from knowledge_flow_backend.core.processors.input.common.enrichment import normalize_enrichment

logger = logging.getLogger(__name__)


class InputConversionError(RuntimeError):
    """
    Raised when an input processor cannot generate a usable preview artifact.
    """


class BaseInputProcessor(ABC):
    """
    Base class for all processors that handle file metadata extraction and processing.
    Creates the initial DocumentMetadata for a newly ingested file.
    """

    description: Optional[str] = None

    # ---------- internal helpers ----------

    def _generate_file_unique_id(self, document_name: str, tags: list[str]) -> str:
        """
        Generate a unique id per ingestion.
        Previously deterministic (name+tags) which caused later ingests to overwrite earlier versions;
        now use a random UUID to keep each ingestion distinct.
        """
        return uuid.uuid4().hex

    @staticmethod
    def _ext_to_filetype(name: str) -> FileType:
        ext = Path(name).suffix.lower().lstrip(".")
        return {
            "pdf": FileType.PDF,
            "docx": FileType.DOCX,
            "pptx": FileType.PPTX,
            "xlsx": FileType.XLSX,
            "csv": FileType.CSV,
            "md": FileType.MD,
            "markdown": FileType.MD,
            "html": FileType.HTML,
            "htm": FileType.HTML,
            "txt": FileType.TXT,
        }.get(ext, FileType.OTHER)

    @staticmethod
    def _hash_file(path: Path, algo: str) -> str | None:
        h = hashlib.new(algo)
        try:
            with path.open("rb") as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    h.update(chunk)
            return h.hexdigest()
        except Exception:
            return None

    @staticmethod
    def _probe_file_info(path: Path) -> tuple[int | None, str | None, str | None, str | None]:
        """
        Returns (size_bytes, mime_type, sha256, md5) using only local filesystem.
        - size: Path.stat()
        - mime: mimetypes.guess_type
        - hashes: streamed (1MB chunks)
        """
        size = None
        mime = None
        sha256 = None
        md5 = None
        try:
            size = path.stat().st_size
        except Exception:
            logger.warning(f"Failed to get size for {path}. File may not exist or is inaccessible.")
            pass
        try:
            mime, _ = mimetypes.guess_type(str(path))
        except Exception:
            logger.warning(f"Failed to guess MIME type for {path}. Using None.")
            pass
        # hashes may be useful later (dedupe, integrity). They’re cheap to compute once here.
        sha256 = BaseInputProcessor._hash_file(path, "sha256")
        md5 = BaseInputProcessor._hash_file(path, "md5")
        return size, mime, sha256, md5

    def _add_common_metadata(self, file_path: Path, tags: list[str], source_tag: str) -> DocumentMetadata:
        """
        Build the v2 nested DocumentMetadata with the minimal facts we know now.
        """
        document_uid = self._generate_file_unique_id(file_path.name, tags)
        source_type: SourceType = resolve_source_type(source_tag)

        identity = Identity(
            document_name=file_path.name,
            document_uid=document_uid,
            title=file_path.stem,  # Using the file name without extension as a default title
        )
        size, mime, sha256, md5 = self._probe_file_info(file_path)
        file = FileInfo(
            file_type=self._ext_to_filetype(file_path.name),  # Pydantic will coerce unknown -> "other"
            mime_type=mime,
            file_size_bytes=size,
            sha256=sha256,
            md5=md5,
        )

        # use the tag store to fetch the tag and get its name
        tags_block = Tagging(
            tag_ids=tags or [],
        )

        source = SourceInfo(
            source_type=source_type,
            source_tag=source_tag,
            pull_location=None,
            retrievable=False,
        )

        return DocumentMetadata(
            identity=identity,
            source=source,
            file=file,
            tags=tags_block,
            # access + processing keep defaults
        )

    def _apply_enrichment(self, meta: DocumentMetadata, enrichment: Dict[str, Any]) -> None:
        """
        Map the flat dict returned by extract_file_metadata() into the nested v2 model.
        Only known keys are applied; unknown keys are ignored.
        """
        if not enrichment:
            return

        # Identity-level fields
        for k in ("title", "author", "created", "modified", "last_modified_by"):
            if k in enrichment and enrichment[k] is not None:
                setattr(meta.identity, k, enrichment[k])

        # File-level fields
        file_map = {
            "mime_type": "mime_type",
            "file_size_bytes": "file_size_bytes",
            "page_count": "page_count",
            "row_count": "row_count",
            "sha256": "sha256",
            "language": "language",
            "file_type": "file_type",  # if your extractor sets a precise type
        }
        for src_key, attr in file_map.items():
            if src_key in enrichment and enrichment[src_key] is not None:
                setattr(meta.file, attr, enrichment[src_key])

        # Source-level optional fields (rare at this stage)
        if "pull_location" in enrichment and enrichment["pull_location"] is not None:
            meta.source.pull_location = enrichment["pull_location"]

        # Tags: allow either ids or names; dedupe is inside Tagging
        if "tag_ids" in enrichment and enrichment["tag_ids"] is not None:
            meta.tags.tag_ids = list(enrichment["tag_ids"])
        if "tag_names" in enrichment and enrichment["tag_names"] is not None:
            meta.tags.tag_names = list(enrichment["tag_names"])

        # Access (optional)
        if "license" in enrichment and enrichment["license"] is not None:
            meta.access.license = enrichment["license"]
        if "confidential" in enrichment and enrichment["confidential"] is not None:
            meta.access.confidential = bool(enrichment["confidential"])
        if "acl" in enrichment and enrichment["acl"] is not None:
            meta.access.acl = list(enrichment["acl"])

        if "extras" in enrichment and enrichment["extras"]:
            # Merge (last writer wins); drop None values to keep it tidy
            clean = {k: v for k, v in enrichment["extras"].items() if v is not None}
            if clean:
                meta.extensions = {**(meta.extensions or {}), **clean}

    # ---------- public API ----------

    def process_metadata(self, file_path: Path, tags: list[str], source_tag: str) -> DocumentMetadata:
        if not self.check_file_validity(file_path):
            raise ValueError(f"File {file_path} is not valid for processing.")

        # 1) Create initial v2 metadata
        base_metadata = self._add_common_metadata(file_path, tags, source_tag)

        # 2) Extract enrichment (title, author, created, sizes, etc.)
        enrichment_raw = self.extract_file_metadata(file_path) or {}
        enrichment = normalize_enrichment(enrichment_raw)

        # 3) Apply enrichment onto the nested model (no dict merges)
        self._apply_enrichment(base_metadata, enrichment)

        # 4) Return the validated model
        return base_metadata

    @abstractmethod
    def check_file_validity(self, file_path: Path) -> bool:
        pass

    @abstractmethod
    def extract_file_metadata(self, file_path: Path) -> dict:
        """
        Return a flat dict of optional fields you discovered.
        Supported keys include (examples, all optional):
          - title, author, created, modified, last_modified_by
          - mime_type, file_size_bytes, page_count, row_count, sha256, language, file_type
          - pull_location
          - tag_ids, tag_names, library_path, library_folder
          - license, confidential, acl
        Unknown keys are ignored.
        """
        pass


class BaseMarkdownProcessor(BaseInputProcessor):
    """For processors that convert to Markdown."""

    @abstractmethod
    def convert_file_to_markdown(self, file_path: Path, output_dir: Path, document_uid: str | None) -> dict:
        """
        Convert the input file to Markdown and save it in the output directory.
        Returns a dict of paths or facts discovered (optional).
        Must raise on failure instead of returning a "status=error" payload.
        """
        pass


class BaseTabularProcessor(BaseInputProcessor):
    """For processors that convert to structured tabular format (e.g., SQL rows)."""

    @abstractmethod
    def convert_file_to_table(self, file_path: Path) -> pandas.DataFrame:
        pass
