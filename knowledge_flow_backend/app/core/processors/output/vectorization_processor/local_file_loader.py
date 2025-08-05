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

from pathlib import Path
from app.common.document_structures import DocumentMetadata
from langchain.schema.document import Document

from app.core.stores.vector.base_vector_store import BaseLangchainDocumentLoader


class LocalFileLoader(BaseLangchainDocumentLoader):
    """
    Local File Loader
    -------------------
    LocalFileLoader is a concrete implementation of DocumentLoaderInterface.
    It loads documents from a local file system. It reads the file content and wraps it in a LangChain Document.

    This class is designed to be used in a vectorization pipeline where documents need to be loaded,
    processed, and stored in a vector store.

    It is a simple implementation that does not require any external dependencies.
    """

    def load_langchain_doc_from_metadata(self, file_path: str, metadata: DocumentMetadata) -> Document:
        """
        Load a document from a local file and wrap it as a LangChain Document.
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"File {file_path} not found.")

        content = path.read_text(encoding="utf-8")

        return Document(page_content=content, metadata=metadata.model_dump(mode="json"))
