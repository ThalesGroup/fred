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

import re
from typing import List, Tuple
from langchain.text_splitter import RecursiveCharacterTextSplitter, MarkdownHeaderTextSplitter
from langchain.schema import Document
from app.core.stores.vector.base_vector_store import BaseTextSplitter


class SemanticSplitter(BaseTextSplitter):
    def __init__(self, chunk_size: int = 1500, chunk_overlap: int = 150):
        """
        Initializes the SemanticSplitter with specified chunk size and overlap.
        Args:
            chunk_size (int, optional): The maximum number of characters in each chunk. Defaults to 1500.
            chunk_overlap (int, optional): The number of overlapping characters between consecutive chunks. Defaults to 150.
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def _extract_and_replace_tables(self, text: str) -> Tuple[str, dict]:
        """
        Extracts annotated Markdown tables from the text and replaces them with unique placeholders.

        Matches tables marked with <!-- TABLE_START:id=... --> and <!-- TABLE_END -->, stores them
        in a dictionary, and replaces each with <<TABLE_id>> in the text.

        Args:
            text (str): Input text containing annotated Markdown tables.

        Returns:
            Tuple[str, dict]:
                - Modified text with table placeholders.
                - Dictionary mapping table IDs to their Markdown content.
        """
        pattern = r"<!-- TABLE_START:id=(.*?) -->\n(.*?)\n<!-- TABLE_END -->"
        table_map = {}

        def replacer(match):
            table_id, table_md = match.group(1), match.group(2)
            table_map[table_id] = table_md.strip()
            return f"<<TABLE_{table_id}>>"

        new_text = re.sub(pattern, replacer, text, flags=re.DOTALL)

        return new_text, table_map

    def _split_large_table(self, table_md: str, table_id: str) -> List[Document]:
        """
        Splits a large Markdown table into smaller chunks based on the configured chunk size.

        Preserves the table header in each chunk and adds metadata including table ID and chunk index.

        Args:
            table_md (str): The Markdown string of the full table.
            table_id (str): The unique identifier for the table.

        Returns:
            List[Document]: A list of Document objects, each containing a chunk of the original table.
        """
        lines = table_md.strip().split("\n")
        if len(lines) < 3:
            return [Document(page_content=table_md, metadata={"is_table": True, "table_id": table_id, "table_chunk_id": 0})]

        header = f"{lines[0]}\n{lines[1]}"
        rows = lines[2:]

        sub_tables = []
        current_rows = []
        chunk_index = 0

        for row in rows:
            if len(header) + len("\n".join(current_rows)) + len(row) > self.chunk_size:
                if current_rows:
                    sub_tables.append(Document(page_content=f"{header}\n{'\n'.join(current_rows)}", metadata={"is_table": True, "table_id": table_id, "table_chunk_id": chunk_index}))
                    chunk_index += 1
                current_rows = [row]
            else:
                current_rows.append(row)

        if current_rows:
            sub_tables.append(Document(page_content=f"{header}\n{'\n'.join(current_rows)}", metadata={"is_table": True, "table_id": table_id, "table_chunk_id": chunk_index}))

        return sub_tables

    def semantic_chunking(self, text: str) -> List[Document]:
        """
        Splits a Markdown document into semantically meaningful chunks with special handling for tables.

        Extracts tables and replaces them with placeholders, splits the text using Markdown headers
        and recursive chunking, then reinserts the tables (splitting large ones if needed).

        Args:
            text (str): The full Markdown text to be chunked.

        Returns:
            List[Document]: A list of Document chunks, including text sections and individual table chunks.
        """

        # 1. Extract tables + replace with placeholder
        text_with_placeholders, table_map = self._extract_and_replace_tables(text)

        # 2. Split text according to Markdown headings
        markdown_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=[
                ("#", "Header 1"),
                ("##", "Header 2"),
                ("###", "Header 3"),
                ("####", "Header 4"),
                ("#####", "Header 5"),
            ],
            strip_headers=False,
        )
        md_chunks = markdown_splitter.split_text(text_with_placeholders)

        # 3. Apply RecursiveCharacterTextSplitter if the chunk is too long
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=self.chunk_size, chunk_overlap=self.chunk_overlap, separators=["\n\n", "\n", " ", ""])
        sub_chunks = []
        for chunk in md_chunks:
            if len(chunk.page_content) > self.chunk_size:
                sub_chunks.extend(text_splitter.split_documents([chunk]))
            else:
                sub_chunks.append(chunk)

        # 4. Reinsert tables
        final_chunks = []
        for chunk in sub_chunks:
            chunk_text = chunk.page_content
            placeholders = re.findall(r"<<TABLE_(.*?)>>", chunk_text)

            if not placeholders:
                final_chunks.append(chunk)
                continue

            # Clean up chunk text
            chunk_text_cleaned = re.sub(r"<<TABLE_.*?>>", "", chunk_text).strip()
            if chunk_text_cleaned:
                chunk.page_content = chunk_text_cleaned
                final_chunks.append(chunk)

            for table_id in placeholders:
                table_md = table_map[table_id]
                if len(table_md) <= self.chunk_size:
                    final_chunks.append(Document(page_content=table_md, metadata={"is_table": True, "table_id": table_id, "table_chunk_id": 0}))
                else:
                    final_chunks.extend(self._split_large_table(table_md, table_id))

        return final_chunks

    def split(self, document: Document) -> List[Document]:
        """
        Splits a document into semantically meaningful chunks and enriches metadata.

        Applies semantic chunking to the document content and adds metadata such as
        original document length and chunk index to each resulting chunk.

        Args:
            document (Document): The input document to split.

        Returns:
            List[Document]: A list of semantically chunked Document objects with enriched metadata.
        """
        semantic_chunks = self.semantic_chunking(document.page_content)
        base_metadata = document.metadata.copy()
        base_metadata["original_doc_length"] = len(document.page_content)

        for chunk_id, chunk in enumerate(semantic_chunks):
            chunk.metadata.update({**base_metadata, "chunk_id": chunk_id})

        return semantic_chunks
