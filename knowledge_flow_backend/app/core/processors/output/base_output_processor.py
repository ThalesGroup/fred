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

from abc import ABC, abstractmethod
import logging

from app.common.document_structures import DocumentMetadata

logger = logging.getLogger(__name__)


class TabularProcessingError(Exception):
    """Raised when a tabular document cannot be processed or saved."""


class VectorProcessingError(Exception):
    """Raised when a vectorization processing fails."""


class BaseOutputProcessor(ABC):
    """
    Base output Processor
    -------------------
    Interface for post-processing files after they have been processed by the extraction processors.
    This interface is designed to be implemented by various concrete classes that handle
    different post-processing tasks (e.g., vectorization, database insertion).
    Design Motivation:
    - Separation of concerns: isolates the post-processing step from the extraction step.
    - Flexibility: allows for different post-processing strategies to be implemented.
    - Testability: enables unit testing of post-processing logic without involving actual file I/O.
    - Uniformity: keeps the processing pipeline modular and easy to extend.
    """

    @abstractmethod
    def process(self, file_path: str, metadata: DocumentMetadata) -> DocumentMetadata:
        """
        Process the file after it has been extracted.
        Args:
            file_path (str): The absolute path of the file to process. If the processor is a vectorization processor,
                             this will be the path to the output file generated by the input processor.

                             If the processor is a database processor, this will be the path to the file to be inserted into the database.
            metadata (DocumentMetadata): Metadata associated with the input file.
        Returns:
            DocumentMetadata: The updated metadata to reflect the progress in processing stages.
        """
        logger.error(f"No implementation found for ouput processor: {file_path} with metadata {metadata}")
        raise NotImplementedError("Output processor not implemented for this file type.")
