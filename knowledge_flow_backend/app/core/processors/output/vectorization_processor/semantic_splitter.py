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
from langchain.text_splitter import RecursiveCharacterTextSplitter, MarkdownHeaderTextSplitter
from langchain.schema import Document

from app.core.stores.vector.base_vector_store import BaseTextSplitter

class SemanticSplitter(BaseTextSplitter):
    
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 100):
        """
        Initializes the SemanticSplitter with specified chunk size and overlap.
        Args:
            chunk_size (int, optional): The maximum number of characters in each chunk. Defaults to 1000.
            chunk_overlap (int, optional): The number of overlapping characters between consecutive chunks. Defaults to 100.
        """
        
        self.chunk_size = chunk_size
        self.overlap = chunk_overlap
    
    def semantic_chunking(self, text: str) -> List[Document]:
        """
        Splits the input text into semantically meaningful chunks using Markdown headers and further subdivides large sections.
        The function first splits the text based on Markdown headers (from level 1 to 5), creating initial document chunks.
        If any chunk exceeds the specified chunk size, it is further split into smaller overlapping chunks using a recursive character-based splitter.
        The result is a list of Document objects, each representing a semantically coherent section of the original text.
        Args:
            text (str): The input text to be chunked.
        Returns:
            List[Document]: A list of Document objects representing the semantically split and size-constrained chunks of the input text.
        """
    
        markdown_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=[
                ("#", "Header 1"),
                ("##", "Header 2"),
                ("###", "Header 3"),
                ("####", "Header 4"),
                ("#####", "Header 5"),
            ]
        )
        
        md_chunks = markdown_splitter.split_text(text)
        
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.overlap,
            separators=["\n\n", "\n", " ", ""]
        )
        
        final_chunks = []
        
        for chunk in md_chunks:
            
            if len(chunk.page_content) > self.chunk_size:
                sub_chunks = text_splitter.split_documents([chunk])
                final_chunks.extend(sub_chunks)
            else:
                final_chunks.append(chunk)
        
        return final_chunks
    
    def split(self, document: Document) -> List[Document]:
        """
        Splits a given document into semantically meaningful chunks and updates their metadata.
        This method uses semantic chunking to divide the input document's content into smaller chunks.
        Each resulting chunk's metadata is updated with the original document length and a unique chunk ID.
        All processed chunks are returned as a list.
        Args:
            document (Document): The document to be split. Must have a 'page_content' attribute.
        Returns:
            List[Document]: A list of semantically split document chunks with updated metadata.
        """
        
        semantic_chunks = self.semantic_chunking(document.page_content)
        
        base_metadata = document.metadata.copy()
        base_metadata['original_doc_length'] = len(document.page_content)
        
        for chunk_id, chunk in enumerate(semantic_chunks):
            chunk.metadata.update({
                **base_metadata,
                'chunk_id': chunk_id
            })
        
        return semantic_chunks
        