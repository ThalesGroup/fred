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
import pathlib
import shutil
import tempfile
from typing import Union
from fastapi import UploadFile

from starlette.datastructures import UploadFile as StarletteUploadFile
from app.application_context import ApplicationContext
from app.core.stores.content.content_storage_factory import get_content_store
from app.features.wip.input_processor_service import InputProcessorService

logger = logging.getLogger(__name__)


class IngestionService:
    """
    A simple service to help ingesting new files.
    ----------------
    This service is responsible for the inital steps of the ingestion process:
    1. Saving the uploaded file to a temporary directory.
    2. Extracting metadata from the file using the appropriate processor based on the file extension.
    """

    def __init__(self):
        self.context = ApplicationContext.get_instance()
        self.processor = InputProcessorService()
        self.storage = get_content_store()

    def save_file_to_temp(self, file: Union[UploadFile, pathlib.Path]) -> pathlib.Path:
        """
        Creates a temporary directory, saves the uploaded file into
        it inside a subdirectory named "ingestion", and returns the full path to the saved file.
        The directory structure will look like this:

            /tmp/abcd1234/
                ├── input
                    └── sample.docx
        """
        # 1. Create the temp directory
        temp_dir = pathlib.Path(tempfile.mkdtemp(), "input")
        temp_dir.mkdir(parents=True, exist_ok=True)

        if isinstance(file, (UploadFile, StarletteUploadFile)):
            file_stream = file.file
            filename = file.filename
        elif isinstance(file, pathlib.Path):
            file_stream = file.open("rb")
            filename = file.name

        # 2. Build the full file path using the original filename
        target_path = temp_dir / filename

        # 3. Copy the file content to the target path
        with open(target_path, "wb") as out_file:
            shutil.copyfileobj(file_stream, out_file)

        if isinstance(file, pathlib.Path):
            file_stream.close()
        # 4. Return the full file path
        logger.info(f"File saved to temporary location: {target_path}")
        return target_path

    def extract_metadata(self, file_path: pathlib.Path, front_metadata: dict) -> dict:
        """
        Extracts metadata from the file using the appropriate processor based on the file extension.
        The metadata is returned as a dictionary.
        The metadata dictionary should contain the following keys:
            - `document_name`: The name of the original file
            - `status`: `"uploaded"` or `"failed"`
            - `document_uid`: The UID of the document if uploaded successfully
            - `error`: The error message if processing failed
        :param file_path: Path to the file from which to extract metadata.
        :param front_metadata: Additional metadata to include in the extraction.
        :return: A dictionary containing the extracted metadata.
        :raises ValueError: If the file format is unsupported or if metadata extraction fails.
        """
        # 1. Get the file extension
        suffix = file_path.suffix.lower()
        processor = self.context.get_input_processor_instance(suffix)
        metadata = processor.process_metadata(file_path, front_metadata)

        if "document_uid" not in metadata:
            raise ValueError("Metadata extraction failed: missing 'document_uid'")

        return metadata
