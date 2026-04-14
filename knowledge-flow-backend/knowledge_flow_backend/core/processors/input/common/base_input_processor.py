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

import duckdb
from tabulate import tabulate

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
    """
    Base class for tabular input processors backed by DuckDB-readable sources.

    Why this exists:
    - The input stage only needs to recognize that one file belongs to the
      tabular ingestion flow.
    - Tabular processors no longer promise a pandas DataFrame preview or an
      `output/table.csv` artifact during input processing.
    - The shared tabular preview path should reuse the same DuckDB-readable
      source description that the Parquet output stage already relies on.

    How to use:
    - Subclass it for processors whose real output is produced later by a
      tabular output processor, typically as a Parquet artifact.
    - Override `build_duckdb_source_relation_sql(...)` when the processor can
      expose a DuckDB relation for bounded preview rendering.
    """

    def build_duckdb_source_relation_sql(self, file_path: Path, *, sample_size: int | None = None) -> str:
        """
        Return the DuckDB relation SQL that reads one tabular source file.

        Why this exists:
        - The Parquet output stage and lightweight preview flows should share
          the same source relation contract instead of materializing pandas
          DataFrames during input processing.

        How to use:
        - Override this method in tabular processors that can expose their
          source file through DuckDB.
        - Return only a relation SQL fragment suitable for `SELECT * FROM ...`.

        Example:
        - `sql = processor.build_duckdb_source_relation_sql(Path("/tmp/data.csv"), sample_size=-1)`
        """
        raise NotImplementedError(f"{self.__class__.__name__} does not expose a DuckDB tabular source relation.")

    def render_markdown_preview(self, file_path: Path, *, max_rows: int, max_cols: int) -> str:
        """
        Render a bounded markdown preview from one DuckDB-readable tabular file.

        Why this exists:
        - Lightweight CSV previews should reuse the same DuckDB-oriented
          ingestion path as the Parquet pipeline instead of loading the full
          source into pandas memory.

        How to use:
        - Pass the local source file path and the desired row/column limits.
        - The preview is read directly from the source relation and never
          persists `output/table.csv`.

        Example:
        - `markdown = processor.render_markdown_preview(Path("/tmp/data.csv"), max_rows=20, max_cols=10)`
        """
        visible_rows = max(0, max_rows)
        visible_cols = max(0, max_cols)
        if visible_rows == 0 or visible_cols == 0:
            return "*Empty CSV*\n"

        relation_sql = self.build_duckdb_source_relation_sql(file_path)
        preview_limit = visible_rows + 1
        connection = duckdb.connect(database=":memory:")
        try:
            preview_query = f"SELECT * FROM {relation_sql} LIMIT {preview_limit}"  # nosec B608
            cursor = connection.execute(preview_query)
            column_names = [str(description[0]) for description in (cursor.description or [])]
            rows = cursor.fetchall()
        finally:
            connection.close()

        if not rows or not column_names:
            return "*Empty CSV*\n"

        truncated_rows = len(rows) > visible_rows
        truncated_cols = len(column_names) > visible_cols
        visible_column_names = column_names[:visible_cols]
        visible_data_rows = [tuple(row[:visible_cols]) for row in rows[:visible_rows]]
        return self._rows_to_markdown_preview(
            column_names=visible_column_names,
            rows=visible_data_rows,
            truncated=truncated_rows or truncated_cols,
        )

    @staticmethod
    def _rows_to_markdown_preview(column_names: list[str], rows: list[tuple[object, ...]], *, truncated: bool) -> str:
        """
        Format one small tabular preview as GitHub-flavored Markdown.

        Why this exists:
        - Tabular previews should be rendered consistently whether they come
          from raw source inspection or later Parquet-backed reads.

        How to use:
        - Pass already-bounded columns and rows.
        - Set `truncated=True` when the caller intentionally omitted extra rows
          or columns from the preview.
        """
        if not column_names:
            return "*Empty CSV*\n"

        def _format_cell(value: object) -> str:
            text = "" if value is None else str(value)
            return text.replace("|", "&#124;").replace("\r\n", " ").replace("\n", " ").replace("\r", " ")

        formatted_headers = [_format_cell(name) for name in column_names]
        formatted_rows = [[_format_cell(cell) for cell in row] for row in rows]
        markdown_table = tabulate(formatted_rows, headers=formatted_headers, tablefmt="github")

        lines = ["", markdown_table]
        if truncated:
            lines.append("... (table truncated)")
        lines.append("")
        return "\n".join(lines) + "\n"
