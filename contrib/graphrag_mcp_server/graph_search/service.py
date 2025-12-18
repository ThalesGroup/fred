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
import json
import logging
from datetime import datetime, timezone
import inspect

from dotenv import load_dotenv
from graphiti_core.nodes import EpisodeType
from graph_search.utils import semantic_chunking


logger = logging.getLogger(__name__)
load_dotenv()


class GraphSearchService:
    """
    High-level service for adding nodes and performing searches
    using Graphiti + Neo4j + OpenAI API.
    """
    def __init__(self):
        import os
        from openai import AsyncOpenAI
        from graphiti_core import Graphiti
        from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
        from graphiti_core.llm_client.config import LLMConfig
        from graphiti_core.llm_client.openai_client import OpenAIClient

        neo4j_uri = os.getenv("NEO4J_URI")
        neo4j_username = os.getenv("NEO4J_USERNAME")
        neo4j_password = os.getenv("NEO4J_PASSWORD")
        model = os.getenv("OPENAI_MODEL")
        embedding_model = os.getenv("OPENAI_EMBEDDING_MODEL")
        api_key = os.getenv("OPENAI_API_KEY")

        self.openai_client = AsyncOpenAI(api_key=api_key)
        llm = OpenAIClient(client=self.openai_client, config=LLMConfig(model=model, small_model=model))
        embedder = OpenAIEmbedder(config=OpenAIEmbedderConfig(embedding_model=embedding_model), client=self.openai_client)
        self.graph = Graphiti(neo4j_uri, neo4j_username, neo4j_password, llm_client=llm, embedder=embedder)
        self._graph_search_center_param: str | None = None

    # -----------------------------------------------------------
    # EPISODE CREATION (TEXT)
    # -----------------------------------------------------------
    async def add_text_node(self, name: str, text: str, description: str = ""):
        await self.graph.add_episode(
            name=name,
            episode_body=text,
            source=EpisodeType.text,
            source_description=description or "text episode",
            reference_time=datetime.now(timezone.utc),
        )
        logger.info(f"Added text node: {name}")

    # -----------------------------------------------------------
    # EPISODE CREATION (JSON)
    # -----------------------------------------------------------
    async def add_json_node(self, name: str, payload: dict, description: str = ""):
        await self.graph.add_episode(
            name=name,
            episode_body=json.dumps(payload),
            source=EpisodeType.json,
            source_description=description or "json episode",
            reference_time=datetime.now(timezone.utc),
        )
        logger.info(f"Added JSON node: {name}")
    
    # -----------------------------------------------------------
    # INGEST FOLDER
    # -----------------------------------------------------------

    async def ingest_folder(self, folder_path: str, chunk_size: int = 1500, chunk_overlap: int = 300):
        """
        Ingest all .md and .pdf files from a folder, chunk them and add as text nodes.
        """
        folder = Path(folder_path)
        if not folder.exists():
            logger.warning(f"Folder does not exist: {folder_path}")
            return

        # Parcours des fichiers
        for ext in ["*.md", "*.txt"]:  # tu peux ajouter "*.pdf" si tu as une fonction de lecture PDF
            for file_path in folder.glob(ext):
                try:
                    text = file_path.read_text(encoding="utf-8")
                except Exception as e:
                    logger.error(f"Failed to read {file_path}: {e}")
                    continue

                chunks = semantic_chunking(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
                logger.info(f"{file_path.name}: {len(chunks)} chunks generated")

                for i, chunk in enumerate(chunks):
                    node_name = f"{file_path.name} - chunk {i + 1}"
                    await self.add_text_node(name=node_name, text=chunk, description=f"Chunked document {file_path.name}")

    # -----------------------------------------------------------
    # SEARCH
    # -----------------------------------------------------------
    async def search_nodes(self, query: str, top_k: int = 5, center_uid: str = ""):
        if top_k > 10:
            raise ValueError("top_k value must under or equal 10")
        if center_uid:
            # Graphiti versions differ: some accept `center_uid`, others don't support centering.
            # We detect support once and fall back gracefully (no centering) when unsupported.
            if self._graph_search_center_param is None:
                try:
                    sig = inspect.signature(self.graph.search)
                    for candidate in ("center_uid", "center_node_uid", "center_id"):
                        if candidate in sig.parameters:
                            self._graph_search_center_param = candidate
                            break
                    else:
                        self._graph_search_center_param = ""
                except Exception:
                    self._graph_search_center_param = ""

            if self._graph_search_center_param:
                try:
                    resp = await self.graph.search(
                        query, **{self._graph_search_center_param: center_uid}
                    )
                except TypeError:
                    logger.info(
                        "Graphiti.search() does not support centering in this version; ignoring center_uid."
                    )
                    self._graph_search_center_param = ""
                    resp = await self.graph.search(query)
            else:
                resp = await self.graph.search(query)
        else:
            resp = await self.graph.search(query)
        return resp[:top_k]

    # -----------------------------------------------------------
    # CLEANUP
    # -----------------------------------------------------------
    async def close(self):
        await self.graph.close()
        logger.info("Connection closed.")
