# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Import the concrete IO base class
import hashlib
import io
import logging
import mimetypes
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, List, Optional, cast  # Added 'cast' here

import pandas as pd

from app.core.stores.content.base_content_store import BaseContentStore, FileMetadata, StoredObjectInfo

logger = logging.getLogger(__name__)


class FileSystemContentStore(BaseContentStore):
    def __init__(self, document_root: Path, object_root: Path):
        self.document_root = document_root
        self.document_root.mkdir(parents=True, exist_ok=True)
        self.object_root = object_root
        self.object_root.mkdir(parents=True, exist_ok=True)
        logger.info(f"📁 Initialized LocalStorageBackend at: {self.document_root} and {self.object_root}")

    def clear(self) -> None:
        """
        Delete every document that was previously saved in this local
        store. Meant for unit-tests; no-op if the folder does not exist.
        """
        if self.document_root.exists():
            shutil.rmtree(self.document_root)
        if self.object_root.exists():
            shutil.rmtree(self.object_root)
        self.document_root.mkdir(parents=True, exist_ok=True)
        self.object_root.mkdir(parents=True, exist_ok=True)
        logger.info("🧹 LocalStorageBackend cleared")

    def save_content(self, document_uid: str, document_dir: Path) -> None:
        destination = self.document_root / document_uid

        # Clean old destination if it exists
        if destination.exists():
            shutil.rmtree(destination)

        # Create destination
        destination.mkdir(parents=True, exist_ok=True)

        logger.info(f"📂 Created destination folder: {destination}")

        # Copy all contents
        for item in document_dir.iterdir():
            target = destination / item.name
            if item.is_dir():
                shutil.copytree(item, target)
                logger.info(f"📁 Copied directory: {item} -> {target}")
            else:
                shutil.copy2(item, target)
                logger.info(f"📄 Copied file: {item} -> {target}")

        logger.info(f"✅ Successfully saved document {document_uid} to {destination}")

    def save_input(self, document_uid: str, input_dir: Path) -> None:
        destination = self.document_root / document_uid / "input"
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(input_dir, destination)

    def save_output(self, document_uid: str, output_dir: Path) -> None:
        destination = self.document_root / document_uid / "output"
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(output_dir, destination)

    def delete_content(self, document_uid: str) -> None:
        """
        Deletes the content directory for the given document UID.
        """
        destination = self.document_root / document_uid

        if destination.exists() and destination.is_dir():
            shutil.rmtree(destination)
            logger.info(f"🗑️ Deleted content for document {document_uid} at {destination}")
        else:
            logger.warning(f"⚠️ Tried to delete content for document {document_uid}, but it does not exist at {destination}")

    def get_content(self, document_uid: str) -> BinaryIO:
        """
        Returns a file stream (BinaryIO) for the first file in the `input` subfolder.
        """
        input_dir = self.document_root / document_uid / "input"
        if not input_dir.exists():
            raise FileNotFoundError(f"No input folder for document: {document_uid}")

        files = list(input_dir.glob("*"))
        if not files:
            raise FileNotFoundError(f"No file found in input folder for document: {document_uid}")

        return open(files[0], "rb")

    def get_markdown(self, document_uid: str) -> str:
        """
        Returns the content of the `output/output.md` file as a UTF-8 string.
        If not found, attempts to convert `output/table.csv` to a Markdown table.
        """
        doc_path = self.document_root / document_uid / "output"
        md_path = doc_path / "output.md"
        csv_path = doc_path / "table.csv"

        if md_path.exists():
            try:
                return md_path.read_text(encoding="utf-8")
            except Exception as e:
                logger.error(f"Error reading markdown file for {document_uid}: {e}")
                raise

        if csv_path.exists():
            try:
                df = pd.read_csv(csv_path)
                if len(df) > 200:
                    df = df.head(200)
                result = df.to_markdown(index=False, tablefmt="github")
                if not result:
                    raise ValueError(f"Markdown conversion resulted in empty content for {document_uid}")
                return result
            except Exception as e:
                logger.error(f"Error reading or converting CSV for {document_uid}: {e}")
                raise

        raise FileNotFoundError(f"Neither markdown nor CSV preview found for document: {document_uid}")

    def get_media(self, document_uid: str, media_id: str) -> BinaryIO:
        """
        Returns a file stream (BinaryIO) for the given file URI.
        """
        return open(self.document_root / document_uid / "output" / "media" / media_id, "rb")

    def get_local_copy(self, document_uid: str, destination_dir: Path) -> Path:
        source_dir = self.document_root / document_uid
        if not source_dir.exists():
            raise FileNotFoundError(f"No stored document for: {document_uid}")
        shutil.copytree(source_dir, destination_dir, dirs_exist_ok=True)
        return destination_dir

    def _get_primary_file_path(self, document_uid: str) -> Path:
        """Helper to find the Path object of the primary input file."""
        input_dir = self.document_root / document_uid / "input"
        if not input_dir.exists():
            raise FileNotFoundError(f"No input folder for document: {document_uid}")

        files = list(input_dir.glob("*"))
        if not files:
            raise FileNotFoundError(f"No file found in input folder for document: {document_uid}")

        return files[0]

    def get_file_metadata(self, document_uid: str) -> FileMetadata:
        """
        Retrieves metadata (size, file_name, content_type) using Python's os.stat.
        Note: Content-Type is set to None here, relying on the service layer to detect/default.
        """
        file_path = self._get_primary_file_path(document_uid)

        # Get file size and name
        size = file_path.stat().st_size
        file_name = file_path.name

        # Construct and return the Pydantic model
        return FileMetadata(
            size=size,
            file_name=file_name,
            content_type=None,  # File system doesn't reliably store MIME type
        )

    def get_content_range(self, document_uid: str, start: int, length: int) -> BinaryIO:
        """
        Streaming range reader for the primary input file (no RAM buffering).
        Returns a BinaryIO stream that limits reads to `length`.
        """
        file_path = self._get_primary_file_path(document_uid)
        f = open(file_path, "rb")
        f.seek(start)

        # Create a wrapper to limit the stream to the requested length (main's version)
        class RangeStreamWrapper(io.IOBase):
            def __init__(self, file_obj: BinaryIO, limit: int):
                self.file_obj = file_obj
                self.bytes_read = 0
                self.limit = limit

                # These binary attributes satisfy the static checker's BinaryIO requirement
                self.mode = "rb"
                self.encoding = None

            def read(self, size: int = -1) -> bytes:
                if self.bytes_read >= self.limit:
                    return b""
                read_size = size if size != -1 else self.limit - self.bytes_read
                bytes_to_read = min(read_size, self.limit - self.bytes_read)
                data = self.file_obj.read(bytes_to_read)
                self.bytes_read += len(data)
                return data

            def close(self):
                self.file_obj.close()

            def readable(self) -> bool:
                return True

            def writable(self) -> bool:
                return False

            def seekable(self) -> bool:
                return self.file_obj.seekable()

        # FIX: Use typing.cast to explicitly assert that this object meets the BinaryIO interface.
        return cast(BinaryIO, RangeStreamWrapper(f, length))

    # ---------- Generic Object API (typed) ----------

    def _key_to_path(self, key: str) -> Path:
        key = (key or "").lstrip("/")
        if not key:
            raise ValueError("Empty object key")
        return self.object_root / key

    def _safe_under(self, base: Path, candidate: Path) -> Path:
        base_r = base.resolve()
        cand_r = candidate.resolve()
        # Ensure candidate path is within the base path
        if not str(cand_r).startswith(str(base_r)):
            raise ValueError("Object key escapes storage root")
        return cand_r

    def put_object(self, key: str, stream: BinaryIO, *, content_type: str) -> StoredObjectInfo:
        """
        Store/replace an arbitrary binary object at 'key'.
        Returns StoredObjectInfo (typed).
        """
        path = self._safe_under(self.object_root, self._key_to_path(key))
        # 🚀 FIX B324: Explicitly mark MD5 as not for security purposes (Python 3.9+)
        # If using < Python 3.9, you'd need to either ignore the warning or switch to SHA256/Blake2b.
        try:
            hasher = hashlib.md5(usedforsecurity=False)
        except TypeError:
            raise RuntimeError("Python 3.9+ is required for secure MD5 hashing in this context")

        size = 0
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as out:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                size += len(chunk)
                hasher.update(chunk)

        stat = path.stat()
        modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)

        return StoredObjectInfo(
            key=key,
            size=size,
            file_name=os.path.basename(path),
            content_type=content_type or mimetypes.guess_type(path.name)[0],
            modified=modified,
            etag=hasher.hexdigest(),
        )

    def get_object_stream(self, key: str, *, start: Optional[int] = None, length: Optional[int] = None) -> BinaryIO:
        """
        Streaming reader for object 'key'. If start/length provided, limit reads accordingly.
        """
        path = self._safe_under(self.object_root, self._key_to_path(key))
        if not path.exists():
            raise FileNotFoundError(f"Object not found: {key}")

        f = open(path, "rb")
        if start is None and length is None:
            return f

        # ranged stream
        f.seek(start or 0)

        # NOTE: Using the RawIOBase/BufferedReader pattern here for the Generic Object API (similar to HEAD)
        # as it was part of the set of new methods.
        class _RangeRaw(io.RawIOBase):
            def __init__(self, base, limit: Optional[int]):
                self._base = base
                self._remaining = limit if limit is not None else float("inf")
                self._closed = False

            def readable(self) -> bool:
                return True

            def readinto(self, b) -> int:
                if self._closed or self._remaining <= 0:
                    return 0
                mv = memoryview(b).cast("B")
                n = min(len(mv), int(self._remaining))
                chunk = self._base.read(n)
                if not chunk:
                    return 0
                r = len(chunk)
                mv[:r] = chunk
                self._remaining -= r
                return r

            def close(self) -> None:
                if not self._closed:
                    try:
                        self._base.close()
                    finally:
                        self._closed = True
                super().close()

            @property
            def closed(self) -> bool:
                return self._closed

        return io.BufferedReader(_RangeRaw(f, length))

    def stat_object(self, key: str) -> StoredObjectInfo:
        """
        Return metadata for object 'key'. Raises FileNotFoundError if absent.
        """
        path = self._safe_under(self.object_root, self._key_to_path(key))
        if not path.exists():
            raise FileNotFoundError(f"Object not found: {key}")
        st = path.stat()
        return StoredObjectInfo(
            key=key,
            size=st.st_size,
            file_name=os.path.basename(path),
            content_type=mimetypes.guess_type(path.name)[0],
            modified=datetime.fromtimestamp(st.st_mtime, tz=timezone.utc),
            etag=None,  # We don't HEAD; if you want stable tags, compute and cache MD5 in a sidecar.
        )

    def list_objects(self, prefix: str) -> List[StoredObjectInfo]:
        """
        Flat, recursive listing under 'prefix'.
        """
        root = self.object_root
        base = self._safe_under(root, root / (prefix or "").lstrip("/"))
        if not base.exists():
            return []

        items: List[StoredObjectInfo] = []
        for p in base.rglob("*"):
            if p.is_file():
                rel_key = str(p.relative_to(root)).replace("\\", "/")
                st = p.stat()
                items.append(
                    StoredObjectInfo(
                        key=rel_key,
                        size=st.st_size,
                        file_name=p.name,
                        content_type=mimetypes.guess_type(p.name)[0],
                        modified=datetime.fromtimestamp(st.st_mtime, tz=timezone.utc),
                        etag=None,
                    )
                )
        return items

    def delete_object(self, key: str) -> None:
        path = self._safe_under(self.object_root, self._key_to_path(key))
        if not path.exists():
            raise FileNotFoundError(f"Object not found: {key}")
        path.unlink()
