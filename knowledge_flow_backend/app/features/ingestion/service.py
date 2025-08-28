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
from app.common.document_structures import DocumentMetadata, ProcessingStage, SourceType
from app.core.processors.input.common.base_input_processor import BaseMarkdownProcessor, BaseTabularProcessor
from app.features.metadata.service import MetadataNotFound, MetadataService

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
        self.content_store = ApplicationContext.get_instance().get_content_store()
        self.metadata_service = MetadataService()

    def save_input(self, metadata: DocumentMetadata, input_dir: pathlib.Path) -> None:
        self.content_store.save_input(metadata.document_uid, input_dir)
        metadata.mark_stage_done(ProcessingStage.RAW_AVAILABLE)

    def save_output(self, metadata: DocumentMetadata, output_dir: pathlib.Path) -> None:
        self.content_store.save_output(metadata.document_uid, output_dir)
        metadata.mark_stage_done(ProcessingStage.PREVIEW_READY)

    def save_metadata(self, metadata: DocumentMetadata) -> None:
        logger.debug(f"Saving metadata {metadata}")
        return self.metadata_service.save_document_metadata(metadata)

    def get_metadata(self, document_uid: str) -> DocumentMetadata | None:
        """
        Retrieve the metadata associated with the given document UID.

        Args:
            document_uid (str): The unique identifier of the document.

        Returns:
            Optional[DocumentMetadata]: The metadata if found, or None if the document
            does not exist in the metadata store.

        Notes:
            If the underlying metadata service raises a `MetadataNotFound` exception,
            this method will return `None` instead of propagating the exception.
        """

        try:
            return self.metadata_service.get_document_metadata(document_uid)
        except MetadataNotFound:
            return None

    def get_local_copy(self, metadata: DocumentMetadata, target_dir: pathlib.Path) -> pathlib.Path:
        """
        Downloads the file content from the store into target_dir and returns the path to the file.
        """
        return self.content_store.get_local_copy(metadata.document_uid, target_dir)

    def extract_metadata(self, file_path: pathlib.Path, tags: list[str], source_tag: str) -> DocumentMetadata:
        """
        Extracts metadata from the input file.
        This method is responsible for determining the file type and using the appropriate processor
        to extract metadata. It also validates the metadata to ensure it contains a document UID.
        """
        suffix = file_path.suffix.lower()
        processor = self.context.get_input_processor_instance(suffix)
        source_config = self.context.get_config().document_sources.get(source_tag)

        # Step 1: run processor
        metadata = processor.process_metadata(file_path, tags=tags, source_tag=source_tag)

        # Step 2: enrich/clean metadata
        if source_config:
            metadata.source.source_type = SourceType(source_config.type)

        # If this is a pull file, preserve the path
        if source_config and source_config.type == "pull":
            metadata.source.pull_location = str(file_path.name)

        # Clean string fields like "None" to actual None
        for field in ["title", "category", "subject", "keywords"]:
            value = getattr(metadata, field, None)
            if isinstance(value, str) and value.strip().lower() == "none":
                setattr(metadata, field, None)

        return metadata

    def process_input(self, input_path: pathlib.Path, output_dir: pathlib.Path, metadata: DocumentMetadata) -> None:
        """
        Processes an input document from input_path and writes outputs to output_dir.
        Saves metadata.json alongside.
        """
        suffix = input_path.suffix.lower()
        processor = self.context.get_input_processor_instance(suffix)

        # 📝 Save metadata.json
        # metadata_path = output_dir / "metadata.json"
        # with open(metadata_path, "w", encoding="utf-8") as meta_file:
        #    json.dump(metadata.model_dump(mode="json"), meta_file, indent=4, ensure_ascii=False)

        # 🗂️ Ensure output directory exists
        output_dir.mkdir(parents=True, exist_ok=True)

        if isinstance(processor, BaseMarkdownProcessor):
            processor.convert_file_to_markdown(input_path, output_dir, metadata.document_uid)
        elif isinstance(processor, BaseTabularProcessor):
            df = processor.convert_file_to_table(input_path)
            df.to_csv(output_dir / "table.csv", index=False)
        else:
            raise RuntimeError(f"Unknown processor type for: {input_path}")

    def process_output(self, input_file_name: str, output_dir: pathlib.Path, input_file_metadata: DocumentMetadata) -> DocumentMetadata:
        """
        Processes data resulting from the input processing.
        """
        suffix = pathlib.Path(input_file_name).suffix.lower()
        processor = self.context.get_output_processor_instance(suffix)
        # check the content of the working dir 'output' directory and if there are some 'output.md' or 'output.csv' files
        # get their path and pass them to the processor
        if not output_dir.exists():
            raise ValueError(f"Output directory {output_dir} does not exist")
        if not output_dir.is_dir():
            raise ValueError(f"Output directory {output_dir} is not a directory")
        # check if the output_dir contains "output.md" or "output.csv" files
        if not any(output_dir.glob("*.*")):
            raise ValueError(f"Output directory {output_dir} does not contain output files")
        # get the first file in the output_dir
        file_to_process = next(output_dir.glob("*.*"))
        # check if the file is a markdown, csv or duckdb file
        if file_to_process.suffix.lower() not in [".md", ".csv", ".duckdb"]:
            raise ValueError(f"Output file {file_to_process} is not a markdown or csv file")
        # check if the file is empty
        if file_to_process.stat().st_size == 0:
            raise ValueError(f"Output file {file_to_process} is empty")
        # check if the file is a markdown or csv file
        file_to_process_abs_str = str(file_to_process.resolve())
        return processor.process(file_path=file_to_process_abs_str, metadata=input_file_metadata)

    def get_markdown(self, metadata: DocumentMetadata, target_dir: pathlib.Path) -> pathlib.Path:
        """
        Downloads the preview file (markdown or CSV) for the document and saves it into `target_dir`.
        Returns the filename of the downloaded preview.
        """
        try:
            # Try markdown first
            md_content = self.content_store.get_markdown(metadata.document_uid)
            target_file = target_dir / "output.md"
            target_file.write_text(md_content, encoding="utf-8")
            logger.info(f"Markdown preview saved to {target_file}")
            return target_file
        except FileNotFoundError:
            raise RuntimeError(f"No preview available for document {metadata.document_uid} in content store")

    def get_preview_file(self, metadata: DocumentMetadata, output_dir: pathlib.Path) -> pathlib.Path:
        """
        Returns the preview file (output.md or table.csv) for a document.
        Raises if not found.
        """
        for name in ["output.md", "table.csv"]:
            candidate = output_dir / name
            if candidate.exists() and candidate.is_file():
                return candidate
        raise FileNotFoundError(f"No preview file found for document: {metadata.document_uid}")
