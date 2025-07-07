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
import shutil
from pathlib import Path
from typing import BinaryIO, List

from app.core.stores.base_knowledge_context_store import BaseKnowledgeContextStore

logger = logging.getLogger(__name__)


class LocalKnowledgeContextStore(BaseKnowledgeContextStore):
    def __init__(self, root_path: Path):
        self.root_path = root_path

    def save_knowledge_context(self, knowledge_context_id: str, directory: Path) -> None:
        destination = self.root_path / knowledge_context_id
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(directory, destination)

    def delete_knowledge_context(self, knowledge_context_id: str) -> None:
        knowledge_context_dir = self.root_path / knowledge_context_id
        if knowledge_context_dir.exists():
            shutil.rmtree(knowledge_context_dir)

    def get_knowledge_context_description(self, knowledge_context_id: str) -> dict:
        desc_path = self.root_path / knowledge_context_id / "knowledge_context.json"
        if not desc_path.exists():
            raise FileNotFoundError("Knowledge_context description not found")
        return json.loads(desc_path.read_text(encoding="utf-8"))

    def get_document(self, knowledge_context_id: str, document_name: str) -> BinaryIO:
        doc_path = self.root_path / knowledge_context_id / "files" / document_name
        if not doc_path.exists():
            raise FileNotFoundError("Document not found in chat knowledge_context")
        return open(doc_path, "rb")

    def list_knowledge_contexts(self, tag: str) -> List[dict]:
        knowledge_contexts = []
        for dir_path in self.root_path.iterdir():
            if dir_path.is_dir():
                knowledge_context_path = dir_path / "knowledge_context.json"
                if knowledge_context_path.exists():
                    try:
                        with open(knowledge_context_path, encoding="utf-8") as f:
                            knowledge_context_data = json.load(f)
                            if knowledge_context_data.get("tag") != tag:
                                continue
                            knowledge_contexts.append(knowledge_context_data)
                    except Exception as e:
                        logger.error(f"Failed to load knowledge_context at {knowledge_context_path}: {e}", exc_info=True)
        return knowledge_contexts

    def list_markdown_files(self, knowledge_context_id: str) -> list[tuple[str, str]]:
        """
        Returns a list of (filename, content) tuples for all markdown files in the knowledge_context's 'files' directory.
        """
        result = []
        files_path = self.root_path / knowledge_context_id / "files"
        if not files_path.exists():
            return result

        for file_path in files_path.glob("*.md"):
            try:
                content = file_path.read_text(encoding="utf-8")
                result.append((file_path.name, content))
            except Exception as e:
                logger.error(f"Failed to read markdown file {file_path}: {e}", exc_info=True)

        return result

    def delete_markdown_file(self, knowledge_context_id: str, document_id: str) -> None:
        file_path = self.root_path / knowledge_context_id / "files" / f"{document_id}.md"
        if file_path.exists():
            file_path.unlink()
