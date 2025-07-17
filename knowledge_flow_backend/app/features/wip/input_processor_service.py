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
import pathlib
from fastapi import UploadFile
from app.application_context import ApplicationContext
from app.core.processors.input.common.base_input_processor import BaseMarkdownProcessor, BaseTabularProcessor


class InputProcessorService:
    """
    Input Processor Service
    ------------------------------------------------------
    This service is responsible for processing the input files and extracting metadata.

    It determines the file type and uses the appropriate processor to extract metadata.
    It also validates the metadata to ensure it contains a document UID.

    What is expected from input processors is to transform the input file into a format
    that can be used by the output processors. As of now, tere are only two output processors:
    1. Markdown processor: generates a well structured markdown file from the input file.
    2. Tabular processor: generates a well structured tabular CSV like format.
    """

    def __init__(self):
        self.context = ApplicationContext.get_instance()

    def extract_metadata(self, file_path: pathlib.Path, front_metadata: dict) -> dict:
        """
        Extracts metadata from the input file.
        This method is responsible for determining the file type and using the appropriate processor
        to extract metadata. It also validates the metadata to ensure it contains a document UID.
        """
        suffix = file_path.suffix.lower()
        processor = self.context.get_input_processor_instance(suffix)
        metadata = processor.process_metadata(file_path, front_metadata)

        if "document_uid" not in metadata:
            raise ValueError("Metadata extraction failed: missing 'document_uid'")

        return metadata

    def process(self, output_dir: pathlib.Path, input_file: str, input_file_metadata: dict) -> None:
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

        # 📝 Save metadata.json
        metadata_path = output_dir / "metadata.json"
        with open(metadata_path, "w", encoding="utf-8") as meta_file:
            json.dump(input_file_metadata, meta_file, indent=4, ensure_ascii=False)

        # 🗂️ Create a dedicated subfolder for the processor's output
        processing_dir = output_dir / "output"
        processing_dir.mkdir(parents=True, exist_ok=True)

        if isinstance(processor, BaseMarkdownProcessor):
            processor.convert_file_to_markdown(file_path, processing_dir, input_file_metadata["document_uid"])
        elif isinstance(processor, BaseTabularProcessor):
            df = processor.convert_file_to_table(file_path)
            df.to_csv(processing_dir / "table.csv", index=False)
        else:
            raise RuntimeError(f"Unknown processor type for: {input_file}")

    async def process_file(self, file: UploadFile, front_metadata: dict, base_temp_dir: pathlib.Path) -> None:
        suffix = pathlib.Path(file.filename).suffix.lower()
        processor = self.context.get_input_processor_instance(suffix)
        output_dir = base_temp_dir / file.filename
        output_dir.mkdir(parents=True, exist_ok=True)

        file_path = output_dir / file.filename
        with open(file_path, "wb") as f:
            f.write(await file.read())

        metadata = processor.process_metadata(file_path, front_metadata)
        document_uid = metadata.get("document_uid")

        if not document_uid:
            raise RuntimeError("Missing document UID in metadata")

        document_dir = output_dir / document_uid
        document_dir.mkdir(parents=True, exist_ok=True)

        metadata_path = document_dir / "metadata.json"
        with open(metadata_path, "w", encoding="utf-8") as meta_file:
            json.dump(metadata, meta_file, indent=4, ensure_ascii=False)

        processor.convert_file_to_markdown(file_path, document_dir, document_uid)
