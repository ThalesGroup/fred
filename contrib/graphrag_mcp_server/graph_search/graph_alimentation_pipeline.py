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

import argparse
import asyncio
from pathlib import Path
from typing import Dict, List

from tqdm import tqdm

from service import GraphSearchService
from graph_search.utils import semantic_chunking


def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument("--folder_path", type=str, default="data/", help="Path to the folder containing the data.")

    parser.add_argument("--chunk_size", type=int, default=1500, help="Chunk size used for splitting text.")

    parser.add_argument("--chunk_overlap", type=int, default=150, help="Chunk overlap used during splitting.")

    return parser.parse_args()


def load_and_chunk_folder(folder_path: str, chunk_size: int = 500, chunk_overlap: int = 50) -> Dict[str, List[str]]:
    """
    Reads all .txt and .md files in a folder, applies semantic_chunking,
    returns dict {filename: [chunks]}.
    """
    folder = Path(folder_path)
    doc_chunks = {}

    for ext in ["*.txt", "*.md"]:
        for file_path in folder.glob(ext):
            text = file_path.read_text(encoding="utf-8")
            chunks = semantic_chunking(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
            doc_chunks[file_path.name] = chunks

    return doc_chunks


# ---------------------------
# Utilisation
# ---------------------------
if __name__ == "__main__":

    async def _main():
        args = parse_args()
        folder_path = args.folder_path
        chunk_size = args.chunk_size
        chunk_overlap = args.chunk_overlap

        service = GraphSearchService()

        # Load and chunk documents
        docs = load_and_chunk_folder(
            folder_path,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

        total_chunks = sum(len(chunks) for chunks in docs.values())

        # Add chunks as Graphiti episodes
        with tqdm(total=total_chunks, desc="Chunk ingestion") as pbar:
            for doc_name, chunks in docs.items():
                for i, chunk in enumerate(chunks, start=1):
                    node_name = f"{doc_name} - chunk {i}"

                    await service.add_text_node(
                        name=node_name,
                        text=chunk,
                        description=f"Chunked document {doc_name}"
                    )

                    pbar.set_postfix(doc=doc_name, chunk=i)
                    pbar.update(1)

                await service.close()
        print("\n✔ Import Done.\n")

    asyncio.run(_main())
