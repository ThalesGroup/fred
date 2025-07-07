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

import shutil
from uuid import uuid4
from pathlib import Path
import tempfile
import json

from fastapi import UploadFile
import logging

from knowledge_flow_app.common.business_exception import KnowledgeContextError, DocumentDeletionError, DocumentNotFound, DocumentProcessingError, KnowledgeContextNotFound, TokenLimitExceeded
from knowledge_flow_app.common.structures import KnowledgeContext, KnowledgeContextDocument
from knowledge_flow_app.common.utils import count_tokens, log_exception, utc_now_iso
from knowledge_flow_app.core.stores.knowledge_context.knowledge_context_storage_factory import get_knowledge_context_store
from knowledge_flow_app.features.wip.input_processor_service import InputProcessorService

logger = logging.getLogger(__name__)


def count_tokens_from_markdown(md_path: Path) -> int:
    text = md_path.read_text(encoding="utf-8")
    return count_tokens(text)


class KnowledgeContextService:
    def __init__(self):
        self.store = get_knowledge_context_store()
        self.processor = InputProcessorService()

    async def list_knowledge_contexts(self, tag: str):
        raw_knowledgeContexts = self.store.list_knowledge_contexts(tag)
        all_knowledgeContexts = []

        for knowledgeContext_data in raw_knowledgeContexts:
            try:
                if knowledgeContext_data.get("tag") != tag:
                    continue

                knowledgeContext_data["created_at"] = knowledgeContext_data.get("created_at", utc_now_iso())
                knowledgeContext_data["updated_at"] = knowledgeContext_data.get("updated_at", utc_now_iso())
                knowledgeContext_data["user_id"] = knowledgeContext_data.get("user_id", "local")
                knowledgeContext_data["tokens"] = knowledgeContext_data.get("tokens", 0)
                knowledgeContext_data["creator"] = knowledgeContext_data.get("creator", "system")

                documents = []
                if "documents" in knowledgeContext_data:
                    documents = [KnowledgeContextDocument(**doc) for doc in knowledgeContext_data["documents"]]

                knowledgeContext = KnowledgeContext(
                    id=knowledgeContext_data["id"],
                    title=knowledgeContext_data.get("title", ""),
                    description=knowledgeContext_data.get("description", ""),
                    created_at=knowledgeContext_data["created_at"],
                    updated_at=knowledgeContext_data["updated_at"],
                    creator=knowledgeContext_data["creator"],
                    user_id=knowledgeContext_data["user_id"],
                    # tokens=knowledgeContext_data["tokens"],
                    documents=documents,
                    tag=knowledgeContext_data["tag"],
                )

                all_knowledgeContexts.append(knowledgeContext)
            except Exception as e:
                logger.error(f"Failed to parse knowledgeContext: {e}", exc_info=True)

        return all_knowledgeContexts

    async def create_knowledge_context(self, title: str, description: str, files_dir: Path, tag: str, file_descriptions: dict[str, str]) -> KnowledgeContext:
        knowledgeContext_id = str(uuid4())

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            knowledgeContext_dir = tmp_path / knowledgeContext_id
            files_subdir = knowledgeContext_dir / "files"
            files_subdir.mkdir(parents=True, exist_ok=True)

            documents = []
            # total_tokens = 0

            for file in files_dir.iterdir():
                if file.is_file():
                    try:
                        processing_dir = tmp_path / f"{file.stem}_processing"
                        processing_dir.mkdir(parents=True, exist_ok=True)

                        input_metadata = {"source_file": file.name, "document_uid": file.stem}

                        temp_input_file = processing_dir / file.name
                        shutil.copy(file, temp_input_file)

                        self.processor.process(output_dir=processing_dir, input_file=file.name, input_file_metadata=input_metadata)

                        output_md = next((processing_dir / "output").glob("*.md"), None)
                        if not output_md:
                            raise FileNotFoundError(f"No .md output found for {file.name}")

                        # token_count = count_tokens_from_markdown(output_md)
                        # if total_tokens + token_count > ApplicationContext.get_instance().get_chat_knowledgeContext_max_tokens():
                        #    raise TokenLimitExceeded()

                        # Only now that we're safe, move the file and record the doc
                        new_md_name = f"{file.stem}.md"
                        dest_path = files_subdir / new_md_name
                        shutil.move(str(output_md), dest_path)

                        # total_tokens += token_count

                        documents.append(
                            KnowledgeContextDocument(
                                id=file.stem,
                                document_name=file.name,
                                document_type=file.suffix[1:],
                                size=file.stat().st_size,
                                # tokens=token_count
                                description=file_descriptions.get(file.name, ""),
                            )
                        )

                    except Exception as e:
                        log_exception(e, "document processing error")
                        raise DocumentProcessingError(file.name) from e

            now = utc_now_iso()
            metadata = {
                "id": knowledgeContext_id,
                "title": title,
                "description": description,
                "created_at": now,
                "updated_at": now,
                "creator": "system",
                "documents": [doc.model_dump() for doc in documents],
                # "tokens": total_tokens,
                "user_id": "local",
                "tag": tag,
            }

            (knowledgeContext_dir / "knowledge_context.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

            self.store.save_knowledge_context(knowledgeContext_id, knowledgeContext_dir)

        return KnowledgeContext(**metadata)

    async def delete_knowledge_context(self, knowledgeContext_id: str):
        try:
            self.store.delete_knowledge_context(knowledgeContext_id)
            return {"success": True}
        except KnowledgeContextError:
            raise  # Let controller decide HTTP mapping
        except Exception as e:
            logger.exception(f"Unexpected error deleting knowledgeContext {knowledgeContext_id}")
            raise KnowledgeContextError("Unexpected error while deleting knowledgeContext") from e

    async def get_knowledge_context_with_markdown(self, knowledgeContext_id: str) -> dict:
        """
        Load knowledgeContext metadata and associated markdown content.
        """
        try:
            knowledgeContext_data = self.store.get_knowledge_context_description(knowledgeContext_id)

            markdown = ""
            if hasattr(self.store, "list_markdown_files"):
                md_files = self.store.list_markdown_files(knowledgeContext_id)
                for filename, content in md_files:
                    markdown += f"\n\n# {filename}\n\n{content}"

            return {"id": knowledgeContext_data["id"], "title": knowledgeContext_data.get("title", ""), "description": knowledgeContext_data.get("description", ""), "markdown": markdown.strip()}

        except Exception as e:
            logger.error(f"Error loading knowledgeContext with markdown: {e}")
            raise

    async def update_knowledge_context(self, knowledgeContext_id: str, title: str, description: str, files: list[UploadFile], document_descriptions: dict) -> KnowledgeContext:
        try:
            try:
                metadata = self.store.get_knowledge_context_description(knowledgeContext_id)
            except FileNotFoundError:
                raise KnowledgeContextNotFound(f"KnowledgeContext '{knowledgeContext_id}' does not exist.")

            metadata["title"] = title
            metadata["description"] = description
            metadata["updated_at"] = utc_now_iso()

            existing_documents = {doc["id"]: doc for doc in metadata.get("documents", [])}
            total_tokens = sum(doc.get("tokens", 0) for doc in existing_documents.values())

            for doc_id, doc in existing_documents.items():
                doc_name = doc.get("document_name")
                new_description = document_descriptions.get(doc_name)
                logger.debug(f"[UPDATE] Checking existing doc '{doc_name}' for new description")
                if new_description is not None:
                    doc["description"] = new_description

            processed_documents = []

            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_path = Path(tmp_dir)

                for upload in files:
                    file_path = tmp_path / upload.filename
                    with open(file_path, "wb") as f:
                        f.write(await upload.read())

                    try:
                        processing_dir = tmp_path / f"{file_path.stem}_processing"
                        processing_dir.mkdir(parents=True, exist_ok=True)
                        shutil.copy(file_path, processing_dir / file_path.name)

                        self.processor.process(output_dir=processing_dir, input_file=file_path.name, input_file_metadata={"source_file": file_path.name, "document_uid": file_path.stem})

                        md_output = next((processing_dir / "output").glob("*.md"), None)
                        if not md_output:
                            raise DocumentProcessingError(f"No markdown generated for '{file_path.name}'")

                        description_value = document_descriptions.get(file_path.name, "")

                        doc = KnowledgeContextDocument(
                            id=file_path.stem, document_name=file_path.name, document_type=file_path.suffix[1:], size=file_path.stat().st_size, description=description_value
                        )

                        existing_documents[doc.id] = doc.model_dump()
                        processed_documents.append((doc.id, md_output))

                    except (DocumentProcessingError, TokenLimitExceeded):
                        raise
                    except Exception as e:
                        logger.error(f"Error processing '{upload.filename}': {e}", exc_info=True)
                        raise DocumentProcessingError(f"Failed to process file '{upload.filename}'") from e

                metadata["tokens"] = total_tokens
                metadata["documents"] = list(existing_documents.values())

                # Prepare new knowledgeContext directory
                knowledgeContext_dir = tmp_path / knowledgeContext_id
                files_dir = knowledgeContext_dir / "files"
                files_dir.mkdir(parents=True, exist_ok=True)

                # Copy existing files not overwritten
                existing_filenames = [f"{doc_id}.md" for doc_id, _ in processed_documents]
                for filename, content in self.store.list_markdown_files(knowledgeContext_id):
                    if filename not in existing_filenames:
                        (files_dir / filename).write_text(content, encoding="utf-8")

                # Copy processed files
                for doc_id, md_file in processed_documents:
                    shutil.copy(md_file, files_dir / f"{doc_id}.md")

                # Save knowledgeContext metadata
                (knowledgeContext_dir / "knowledge_context.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
                self.store.save_knowledge_context(knowledgeContext_id, knowledgeContext_dir)

            return KnowledgeContext(**metadata)

        except KnowledgeContextError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error while updating knowledgeContext '{knowledgeContext_id}': {e}", exc_info=True)
            raise DocumentProcessingError("Unexpected internal error during knowledgeContext update.") from e

    async def delete_document(self, knowledgeContext_id: str, document_id: str):
        try:
            try:
                metadata = self.store.get_knowledge_context_description(knowledgeContext_id)
            except FileNotFoundError:
                raise KnowledgeContextNotFound(f"Profile '{knowledgeContext_id}' not found")

            documents = metadata.get("documents", [])
            matching = [doc for doc in documents if doc["id"] == document_id]
            if not matching:
                raise DocumentNotFound(f"Document '{document_id}' not found in knowledgeContext '{knowledgeContext_id}'")

            # Remove document entry
            updated_documents = [doc for doc in documents if doc["id"] != document_id]
            metadata["documents"] = updated_documents
            metadata["updated_at"] = utc_now_iso()

            # Recalculate tokens
            # total_tokens = 0
            # for doc in updated_documents:
            #     try:
            #         with self.store.get_document(knowledgeContext_id, f"{doc['id']}.md") as f:
            #             content = f.read().decode("utf-8")
            #             tokens = count_tokens(content)
            #             doc["tokens"] = tokens
            #             total_tokens += tokens
            #     except Exception as e:
            #         logger.warning(f"Could not read markdown for token count: {e}")

            # metadata["tokens"] = total_tokens

            # Delete markdown file
            if hasattr(self.store, "delete_markdown_file"):
                try:
                    self.store.delete_markdown_file(knowledgeContext_id, document_id)
                except Exception as e:
                    logger.warning(f"Failed to delete markdown file for {document_id}: {e}")
                    raise DocumentDeletionError(f"Failed to delete markdown file: {e}")

            # Reconstruct knowledgeContext dir
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_path = Path(tmp_dir)
                knowledgeContext_dir = tmp_path / knowledgeContext_id
                files_dir = knowledgeContext_dir / "files"
                files_dir.mkdir(parents=True, exist_ok=True)

                for doc in updated_documents:
                    filename = f"{doc['id']}.md"
                    try:
                        with self.store.get_document(knowledgeContext_id, filename) as f:
                            content = f.read().decode("utf-8")
                            (files_dir / filename).write_text(content, encoding="utf-8")
                    except Exception as e:
                        logger.warning(f"Could not copy file {filename}: {e}")

                (knowledgeContext_dir / "knowledge_context.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
                self.store.save_knowledge_context(knowledgeContext_id, knowledgeContext_dir)

            return {"success": True}

        except KnowledgeContextError:
            raise
        except Exception as e:
            logger.exception(f"Unexpected error deleting document '{document_id}' from knowledgeContext '{knowledgeContext_id}'")
            raise DocumentDeletionError("Unexpected error during document deletion") from e
