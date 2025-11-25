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
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Sequence

from knowledge_flow_backend.common.document_structures import DocumentMetadata

logger = logging.getLogger(__name__)


@dataclass
class LibraryDocumentInput:
    """
    Container for corpus-level processing: the absolute path to the processed
    preview (e.g., markdown) plus the associated metadata.
    """

    file_path: str
    metadata: DocumentMetadata


class LibraryOutputProcessor(ABC):
    """
    Corpus-level output processor.

    This runs once for a library/corpus and can aggregate information across
    multiple documents (e.g., build a shared graph). It is intentionally
    separate from BaseOutputProcessor, which is strictly per-document.
    """

    description: Optional[str] = None

    @abstractmethod
    def process_library(
        self,
        documents: Sequence[LibraryDocumentInput],
        library_tag: str | None = None,
    ) -> List[DocumentMetadata]:
        """
        Process a batch of documents belonging to the same library/corpus.

        Args:
            documents: Sequence of processed document previews + metadata.
            library_tag: Optional library identifier for namespacing outputs.
        Returns:
            List[DocumentMetadata]: Updated metadata for each document.
        """
        logger.error("No implementation found for corpus processor.")
        raise NotImplementedError("Corpus output processor not implemented.")
