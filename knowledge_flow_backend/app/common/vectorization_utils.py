from pathlib import Path

from app.common.document_structures import DocumentMetadata
from langchain.schema.document import Document


def load_langchain_doc_from_metadata(file_path: str, metadata: DocumentMetadata) -> Document:
    """
    Load a document from a local file and wrap it as a LangChain Document.
    Args:
        file_path (str): The path to the file to load.
        metadata (DocumentMetadata): Metadata associated with the document.
    Returns:
        Document: A LangChain Document containing the file content and metadata.
    Raises:
        FileNotFoundError: If the specified file does not exist.
    """

    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"File {file_path} not found.")

    content = path.read_text(encoding="utf-8")
    return Document(page_content=content, metadata=metadata.model_dump(mode="json"))
