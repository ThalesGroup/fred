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

from typing import List
from langchain.schema.document import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter

from app.core.processors.output.vectorization_processor.interfaces import BaseTextSplitter



class RecursiveSplitter(BaseTextSplitter):
    """
    Concrete implementation of TextSplitterInterface using LangChain's
    RecursiveCharacterTextSplitter.

    This splitter breaks long documents into smaller chunks based on character limits,
    attempting to preserve semantic boundaries (e.g., paragraph breaks).

    Chunk size and overlap are adjustable if needed later.
    """

    def __init__(self, chunk_size: int = 2000, chunk_overlap: int = 100):
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    def split(self, document: Document) -> List[Document]:
        """
        Split a document into smaller chunks using RecursiveCharacterTextSplitter.

        Args:
            document (Document): The original full document.

        Returns:
            List[Document]: A list of smaller chunked documents.
        """
        return self.splitter.split_documents([document])
