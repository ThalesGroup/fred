# code_search/code_loader.py
import logging
import os
from langchain.schema.document import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)

VALID_EXTENSIONS = {".java", ".xml", ".properties", ".md", ".txt", ".yaml"}

def load_code_documents(root_dir: str) -> list[Document]:
    documents = []
    splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        chunk_size=1024,
        chunk_overlap=100,
    )

    for dirpath, _, filenames in os.walk(root_dir):
        if any(x in dirpath for x in ["target", ".git", "build"]):
            continue

        for fname in filenames:
            ext = os.path.splitext(fname)[1]
            if ext not in VALID_EXTENSIONS:
                continue

            full_path = os.path.join(dirpath, fname)
            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    content = f.read()

                splits = splitter.split_text(content)
                for i, chunk in enumerate(splits):
                    documents.append(Document(
                        page_content=chunk,
                        metadata={
                            "source": full_path,
                            "file_name": fname,
                            "language": guess_language(fname),
                            "symbol": None,  # optional improvement
                            "document_uid": f"{full_path}#{i}",
                            "embedding_model": "code",  # optional
                            "vector_index": "codebase",
                        }
                    ))

            except Exception as e:
                logger.info(f"⚠️ Skipped file: {full_path} due to {e}")
    return documents


def guess_language(filename: str) -> str:
    if filename.endswith(".java"):
        return "Java"
    elif filename.endswith(".xml"):
        return "XML"
    elif filename.endswith(".properties"):
        return "Properties"
    elif filename.endswith(".md"):
        return "Markdown"
    return "PlainText"
