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

import os
import json
import logging
from datetime import datetime, timezone

from dotenv import load_dotenv
from openai import AsyncOpenAI

from graphiti_core import Graphiti
from graphiti_core.search.search_config import SearchConfig
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.llm_client.openai_client import OpenAIClient
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.nodes import EpisodeType

logger = logging.getLogger(__name__)
load_dotenv()


class GraphSearchService:
    """
    High-level service for adding nodes and performing searches
    using Graphiti + Neo4j + OpenAI API.
    """

    def __init__(self):
        # ---- Neo4j ----
        neo4j_uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
        neo4j_user = os.environ.get("NEO4J_USER", "neo4j")
        neo4j_password = os.environ.get("NEO4J_PASSWORD", "password")

        # ---- OpenAI ----
        api_key = os.environ.get("OPENAI_API_KEY")
        model = os.environ.get("OPENAI_MODEL", "gpt-5-mini")
        embedding_model = os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

        # ---- Others ----
        telemetry = os.environ.get("GRAPHITI_TELEMETRY_ENABLED")
        search_limit = os.environ.get("DEFAULT_SEARCH_LIMIT")

        if not api_key:
            raise ValueError("OPENAI_API_KEY must be set")

        # ---- OpenAI client ----
        self.openai_client = AsyncOpenAI(api_key=api_key)

        # ---- LLM + Embedding clients ----
        llm = OpenAIClient(
            client=self.openai_client,
            config=LLMConfig(model=model, small_model=model),
        )

        embedder_config = OpenAIEmbedderConfig(embedding_model=embedding_model)
        embedder = OpenAIEmbedder(
            config = embedder_config,
            client=self.openai_client
        )

        # ---- Graphiti ----
        self.graph = Graphiti(
            neo4j_uri,
            neo4j_user,
            neo4j_password,
            llm_client=llm,
            embedder=embedder,
        )

        logger.info("GraphSearchService initialized (using OpenAI API).")

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
    # SEARCH
    # -----------------------------------------------------------
    async def search_nodes(self, query: str, top_k: int = 5, center_uid: str = "" ):
        if top_k >10 :
            raise ValueError("top_k value must under or equal 10")
        if center_uid !="":
            resp = await self.graph.search(query, center_uid=center_uid)
        else :
            resp = await self.graph.search(query) 
        return resp[:top_k]

    # -----------------------------------------------------------
    # CLEANUP
    # -----------------------------------------------------------
    async def close(self):
        await self.graph.close()
        logger.info("Connection closed.")