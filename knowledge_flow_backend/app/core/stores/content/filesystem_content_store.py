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

import logging
import shutil
from pathlib import Path
from typing import BinaryIO

import pandas as pd

from app.core.stores.content.base_content_store import BaseContentStore, FileMetadata

logger = logging.getLogger(__name__)


class FileSystemContentStore(BaseContentStore):
    def __init__(self, destination_root: Path):
        self.destination_root = destination_root

    def clear(self) -> None:
        """
        Delete every document that was previously saved in this local
        store.  Meant for unit-tests; no-op if the folder does not exist.
        """
        if self.destination_root.exists():
            shutil.rmtree(self.destination_root)
        self.destination_root.mkdir(parents=True, exist_ok=True)
        logger.info("🧹 LocalStorageBackend cleared")

    def save_content(self, document_uid: str, document_dir: Path) -> None:
        destination = self.destination_root / document_uid

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
        destination = self.destination_root / document_uid / "input"
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(input_dir, destination)

    def save_output(self, document_uid: str, output_dir: Path) -> None:
        destination = self.destination_root / document_uid / "output"
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(output_dir, destination)

    def delete_content(self, document_uid: str) -> None:
        """
        Deletes the content directory for the given document UID.
        """
        destination = self.destination_root / document_uid

        if destination.exists() and destination.is_dir():
            shutil.rmtree(destination)
            logger.info(f"🗑️ Deleted content for document {document_uid} at {destination}")
        else:
            logger.warning(f"⚠️ Tried to delete content for document {document_uid}, but it does not exist at {destination}")

    def get_content(self, document_uid: str) -> BinaryIO:
        """
        Returns a file stream (BinaryIO) for the first file in the `input` subfolder.
        """
        input_dir = self.destination_root / document_uid / "input"
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
        doc_path = self.destination_root / document_uid / "output"
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
        return open(self.destination_root / document_uid / "output" / "media" / media_id, "rb")

    def get_local_copy(self, document_uid: str, destination_dir: Path) -> Path:
        source_dir = self.destination_root / document_uid
        if not source_dir.exists():
            raise FileNotFoundError(f"No stored document for: {document_uid}")
        shutil.copytree(source_dir, destination_dir, dirs_exist_ok=True)
        return destination_dir

    def _get_primary_file_path(self, document_uid: str) -> Path:
        """Helper to find the Path object of the primary input file."""
        input_dir = self.destination_root / document_uid / "input"
        if not input_dir.exists():
            raise FileNotFoundError(f"No input folder for document: {document_uid}")

        files = list(input_dir.glob("*"))
        if not files:
            raise FileNotFoundError(f"No file found in input folder for document: {document_uid}")

        return files[0]

    # --------------------------------------------------------------------------
    # NEW METHODS FOR STREAMING/RANGE REQUESTS
    # --------------------------------------------------------------------------

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
        Retrieves a readable binary stream for a specific byte range by opening
        the file, seeking to the start, and creating a limited stream reader.
        """
        file_path = self._get_primary_file_path(document_uid)

        # 1. Open the file in binary read mode ('rb')
        f = open(file_path, "rb")

        # 2. Seek to the requested start position
        f.seek(start)

        # 3. Create a wrapper to limit the stream to the requested length
        # io.BufferedReader is useful, but a simple wrapper is clearer:

        # A simple lambda/inner class is often used, but returning the opened,
        # correctly-positioned file object and relying on the FastAPI
        # StreamingResponse to handle the length limit is common.

        # For a truly robust stream limited to 'length' bytes:
        class RangeStreamWrapper(BinaryIO):
            def __init__(self, file_obj: BinaryIO, limit: int):
                self.file_obj = file_obj
                self.bytes_read = 0
                self.limit = limit

            def read(self, size: int = -1) -> bytes:
                if self.bytes_read >= self.limit:
                    return b""

                # Determine how much to read, maxing out at 'size' or remaining limit
                read_size = size if size != -1 else self.limit - self.bytes_read
                bytes_to_read = min(read_size, self.limit - self.bytes_read)

                data = self.file_obj.read(bytes_to_read)
                self.bytes_read += len(data)

                return data

            def close(self):
                self.file_obj.close()

            # Implement other BinaryIO methods for full compliance (e.g., seek, tell, readable)
            def seek(self, *args, **kwargs):
                return self.file_obj.seek(*args, **kwargs)

            def tell(self):
                return self.file_obj.tell()

        # Return the wrapped stream
        return RangeStreamWrapper(f, length)
