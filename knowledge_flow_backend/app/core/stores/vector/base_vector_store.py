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

"""
Vectorization Architecture

High-Level Schema:

 [ FILE PATH + METADATA ]
             │
             ▼
┌───────────────────────────────┐
│    DocumentLoaderInterface    │  (ex: LocalFileLoader)
└───────────────────────────────┘
             │
             ▼
┌───────────────────────────────┐
│     TextSplitterInterface     │  (ex: RecursiveSplitter)
└───────────────────────────────┘
             │
             ▼
┌───────────────────────────────┐
│   EmbeddingModelInterface     │  (ex: AzureEmbedder)
└───────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────┐
│        VectorStoreInterface         │  (ex: TracedOpenSearchVectorStore)
└─────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────┐
│        BaseMetadataStore            │  (ex: OpenSearchMetadataStore)
└─────────────────────────────────────┘

Each step is handled by a modular, replaceable component.
This design allows easy switching of backends (e.g., OpenSearch ➔ ChromaDB, Azure ➔ HuggingFace).

"""

from abc import ABC, abstractmethod
from typing import List, Tuple
from app.common.document_structures import DocumentMetadata
from langchain.schema.document import Document


class BaseDocumentLoader(ABC):
    """
    Interface for loading documents from a given source and returning them as LangChain Documents.
    This interface is designed to be implemented by various concrete classes that handle
    different document sources (e.g., local files, remote files, APIs).

    Design Motivation:
    -------------------
    Although in the current system documents are always processed from local files,
    we define this interface to maintain clear separation of concerns:

    - The "loading" step (reading raw content + associating metadata) is isolated.
    - Future flexibility: easily swap in other sources (e.g., S3, Minio, remote API, database).
    - Testability: mock the loading phase during unit testing without involving actual file I/O.
    - Uniformity: keeps the vectorization pipeline modular and easy to extend.

    Every concrete implementation must return a LangChain `Document`
    containing the loaded text and its associated metadata.

    Typical implementations:
    -------------------------
    - LocalFileLoader (reads from local disk)
    - RemoteFileLoader (future: reads from S3/Minio)
    - APIDocumentLoader (future: fetches from an API)

    """

    @abstractmethod
    def load(self, file_path: str, metadata: DocumentMetadata) -> Document:
        """Load a document from a file."""
        pass


# 2. Text Splitter Interface
class BaseTextSplitter(ABC):
    """
    Interface for splitting documents into smaller chunks.
    This interface is designed to be implemented by various concrete classes that handle
    different splitting strategies (e.g., by character, by sentence, etc.).
    """

    @abstractmethod
    def split(self, document: Document) -> List[Document]:
        """Split a document into smaller chunks."""
        pass


# 3. Embedding Model Interface
class BaseEmbeddingModel(ABC):
    """
    Interface for embedding models.
    This interface is designed to be implemented by various concrete classes that handle
    different embedding strategies (e.g., OpenAI, Azure, HuggingFace, etc.).
    """

    @abstractmethod
    def embed_documents(self, documents: List[Document]) -> List[dict]:
        """
        Embed a list of documents into vectors.
        Returns a list of { 'embedding': List[float], 'document': Document }
        """
        pass


# 4. Vector Store Interface
class BaseVectoreStore(ABC):
    """
    Base Vector Store
    -------------------
    Interface for vector stores.

    This interface is designed to be implemented by various concrete classes that handle
    different vector storage strategies (e.g., OpenSearch, in memory, etc.).
    """

    @abstractmethod
    def add_documents(self, documents: List[Document]) -> None:
        """Store the documents in a vector database."""
        pass

    @abstractmethod
    def similarity_search_with_score(self, query: str, k: int = 5) -> List[Tuple[Document, float]]:
        """
        Perform a similarity search on the vector store.

        Args:
            query (str): The query string.
            k (int): Number of top documents to return.

        Returns:
            List[Tuple[Document, float]]: A list of tuples containing the document and its similarity score.
        """
        pass
