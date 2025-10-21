# app/core/agents/store/opensearch_agent_store.py
# Copyright Thales 2025
# Apache-2.0

from __future__ import annotations

import logging
from typing import List, Optional

from fred_core import validate_index_mapping
from opensearchpy import NotFoundError, OpenSearch, RequestsHttpConnection
from pydantic import TypeAdapter

# ⬇️ IMPORTANT: new location that defines the union AgentSettings = Annotated[Union[Agent, Leader], ...]
from agentic_backend.common.structures import AgentSettings
from agentic_backend.core.agents.store.base_agent_store import BaseAgentStore

logger = logging.getLogger(__name__)

# Why this mapping:
# - We keep only fields present in the new BaseAgent/Agent/Leader model tree.
# - Strings we filter on (name, type, role, tags) are keywords.
# - Human text (description) is text.
# - Complex configs (model, tuning, mcp_servers) stay enabled objects for retrieval.
AGENTS_INDEX_MAPPING = {
    "mappings": {
        "dynamic": False,
        "properties": {
            "name": {"type": "keyword"},
            "type": {"type": "keyword"},  # "agent" | "leader" (discriminator)
            "enabled": {"type": "boolean"},
            "tags": {
                "type": "keyword"
            },  # replaces previous singular "tag"/"categories"
            "role": {"type": "keyword"},  # user-facing “what it is”
            "description": {"type": "text"},  # human text
            "class_path": {"type": "keyword", "null_value": "null"},
            "model": {"type": "object", "enabled": True},
            "tuning": {"type": "object", "enabled": True},
            "mcp_servers": {
                "type": "object",
                "enabled": True,
            },  # not nested until we need nested queries
        },
    }
}

# Discriminated-union (de)serializer
AgentSettingsAdapter = TypeAdapter(AgentSettings)


class OpenSearchAgentStore(BaseAgentStore):
    """
    Fred rationale:
    - Agents are keyed by `name` (document ID).
    - We store the Pydantic-union payload as-is; mapping exposes only filter/search fields.
    """

    def __init__(
        self,
        host: str,
        index: str,
        username: str,
        password: str,
        secure: bool = False,
        verify_certs: bool = False,
    ):
        self.client = OpenSearch(
            host,
            http_auth=(username, password),
            use_ssl=secure,
            verify_certs=verify_certs,
            connection_class=RequestsHttpConnection,
        )
        self.index_name = index

        if not self.client.indices.exists(index=self.index_name):
            self.client.indices.create(index=self.index_name, body=AGENTS_INDEX_MAPPING)
            logger.info(f"[AGENTS] OpenSearch index '{self.index_name}' created.")
        else:
            logger.info(
                f"[AGENTS] OpenSearch index '{self.index_name}' already exists."
            )
            validate_index_mapping(self.client, self.index_name, AGENTS_INDEX_MAPPING)

    # ---------------- CRUD ----------------

    def save(self, settings: AgentSettings) -> None:
        """
        Why model_dump(mode='json'):
        - Ensures union payload (with 'type' discriminator) is serialized consistently
          and excludes pydantic internals.
        """
        try:
            body = AgentSettingsAdapter.dump_python(
                settings, mode="json", exclude_none=True
            )
            self.client.index(index=self.index_name, id=settings.name, body=body)
            logger.info(f"[AGENTS] Agent '{settings.name}' saved")
        except Exception as e:
            logger.error(f"[AGENTS] Failed to save agent '{settings.name}': {e}")
            raise

    def load_all(self) -> List[AgentSettings]:
        """
        We keep it simple (<=1000). If you expect more, switch to scroll or search_after.
        """
        try:
            result = self.client.search(
                index=self.index_name,
                body={"query": {"match_all": {}}},
                params={"size": 1000},
            )
            docs = [hit["_source"] for hit in result["hits"]["hits"]]
            # ⬇️ Union-safe validation
            return [AgentSettingsAdapter.validate_python(doc) for doc in docs]
        except Exception as e:
            logger.error(f"[AGENTS] Failed to list agents: {e}")
            raise

    def get(self, name: str) -> Optional[AgentSettings]:
        """
        Union-safe load using TypeAdapter.
        """
        try:
            result = self.client.get(index=self.index_name, id=name)
            return AgentSettingsAdapter.validate_python(result["_source"])
        except NotFoundError:
            return None
        except Exception as e:
            logger.error(f"[AGENTS] Failed to get agent '{name}': {e}")
            raise

    def delete(self, name: str) -> None:
        try:
            self.client.delete(index=self.index_name, id=name)
            logger.info(f"[AGENTS] Deleted agent '{name}'")
        except NotFoundError:
            logger.warning(f"[AGENTS] Agent '{name}' not found for deletion")
        except Exception as e:
            logger.error(f"[AGENTS] Failed to delete agent '{name}': {e}")
            raise
