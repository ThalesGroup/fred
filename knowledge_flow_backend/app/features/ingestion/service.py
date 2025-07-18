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

import json
import logging
import pathlib
import shutil
import tempfile
from typing import Union
from app.common.structures import DocumentMetadata, OutputProcessorResponse
from app.core.processors.input.common.base_input_processor import BaseMarkdownProcessor, BaseTabularProcessor
from fastapi import UploadFile

from starlette.datastructures import UploadFile as StarletteUploadFile
from app.application_context import ApplicationContext

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
        self.storage = ApplicationContext.get_instance().get_content_store()

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

    def extract_metadata(self, file_path: pathlib.Path, tags: list[str]) -> DocumentMetadata:
        """
        Extracts metadata from the input file.
        This method is responsible for determining the file type and using the appropriate processor
        to extract metadata. It also validates the metadata to ensure it contains a document UID.
        """
        suffix = file_path.suffix.lower()
        processor = self.context.get_input_processor_instance(suffix)
        metadata = processor.process_metadata(file_path, tags=tags)
        return metadata

    def process_input(self, output_dir: pathlib.Path, input_file: str, metadata: DocumentMetadata) -> None:
        """
        Processes input document
        ------------------------------------------------------
        1. Extracts metadata from the input file.
        2. Converts the file to markdown or tabular format.
        3. Saves the converted file and metadata in a structured directory.

        Given the temp_dir, filename and metadata (with document_uid), run the appropriate processor.
        Returns the document directory path with results.
        The directory structure will look like this:

            /tmp/abcd1234/
                ├── input
                │   └── sample.docx
                ├── output
                │   └── file.md or table.csv or other
                └── metadata.json
        """
        suffix = pathlib.Path(input_file).suffix.lower()
        processor = self.context.get_input_processor_instance(suffix)
        file_path = output_dir / input_file

        # 📝 Save metadata.json. This is a duplicate of the metadata stored in the
        # global metadata store
        metadata_path = output_dir / "metadata.json"
        with open(metadata_path, "w", encoding="utf-8") as meta_file:
            json.dump(metadata.model_dump(mode="json"), meta_file, indent=4, ensure_ascii=False)


        # 🗂️ Create a dedicated subfolder for the processor's output
        processing_dir = output_dir / "output"
        processing_dir.mkdir(parents=True, exist_ok=True)

        if isinstance(processor, BaseMarkdownProcessor):
            processor.convert_file_to_markdown(file_path, processing_dir, metadata.document_uid)
        elif isinstance(processor, BaseTabularProcessor):
            df = processor.convert_file_to_table(file_path)
            df.to_csv(processing_dir / "table.csv", index=False)
        else:
            raise RuntimeError(f"Unknown processor type for: {input_file}")

    def process_output(self, working_dir: pathlib.Path, input_file: str, input_file_metadata: DocumentMetadata) -> OutputProcessorResponse:
        """
        Processes data resulting from the input processing.
        """
        suffix = pathlib.Path(input_file).suffix.lower()
        processor = self.context.get_output_processor_instance(suffix)
        # check the content of the working dir 'output' directory and if there are some 'output.md' or 'output.csv' files
        # get their path and pass them to the processor
        output_dir = working_dir / "output"
        if not output_dir.exists():
            raise ValueError(f"Output directory {output_dir} does not exist")
        if not output_dir.is_dir():
            raise ValueError(f"Output directory {output_dir} is not a directory")
        # check if the output_dir contains "output.md" or "output.csv" files
        if not any(output_dir.glob("*.*")):
            raise ValueError(f"Output directory {output_dir} does not contain output files")
        # get the first file in the output_dir
        output_file = next(output_dir.glob("*.*"))
        # check if the file is a markdown or csv file
        if output_file.suffix.lower() not in [".md", ".csv"]:
            raise ValueError(f"Output file {output_file} is not a markdown or csv file")
        # check if the file is empty
        if output_file.stat().st_size == 0:
            raise ValueError(f"Output file {output_file} is empty")
        # check if the file is a markdown or csv file
        return processor.process(output_file, input_file_metadata)