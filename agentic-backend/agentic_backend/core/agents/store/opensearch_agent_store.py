# agentic_backend/core/agents/store/opensearch_agent_store.py
# Copyright Thales 2025
# Apache-2.0

from __future__ import annotations

import logging
from typing import List, Optional, Tuple  # Added Tuple, Any for save_all fix

from fred_core import validate_index_mapping
from opensearchpy import NotFoundError, OpenSearch, RequestsHttpConnection, exceptions
from pydantic import TypeAdapter

from agentic_backend.common.structures import AgentSettings
from agentic_backend.core.agents.agent_spec import (
    AgentTuning,  # Import the Tuning model
)
from agentic_backend.core.agents.store.base_agent_store import (
    SCOPE_GLOBAL,
    BaseAgentStore,
)

logger = logging.getLogger(__name__)

# --- NEW MAPPING FIELDS ---
AGENTS_INDEX_MAPPING = {
    "mappings": {
        "dynamic": False,
        "properties": {
            # New Scope Fields
            "scope": {"type": "keyword"},
            # NOTE: For GLOBAL scope (scope_id=None), OpenSearch stores the field as null
            # The mapping's "null_value": "null" ensures a query for "scope_id":"null" finds it.
            "scope_id": {"type": "keyword", "null_value": "null"},
            # Existing Fields (Rest of the Pydantic model is stored in _source)
            "name": {"type": "keyword"},
            "type": {"type": "keyword"},
            "enabled": {"type": "boolean"},
            "tags": {"type": "keyword"},
            "role": {"type": "keyword"},
            "description": {"type": "text"},
            "class_path": {"type": "keyword", "null_value": "null"},
            "model": {"type": "object", "enabled": True},
            "tuning": {"type": "object", "enabled": True},
            "mcp_servers": {"type": "object", "enabled": True},
        },
    }
}

AgentSettingsAdapter = TypeAdapter(AgentSettings)


class OpenSearchAgentStore(BaseAgentStore):
    """
    Agent store using OpenSearch, now supporting GLOBAL and USER scopes.
    Documents are keyed by a composite ID: '<agent_name>:<scope>:<scope_id>'
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

        # --- Backward Compatibility: Update Mapping on Existing Index ---
        if self.client.indices.exists(index=self.index_name):
            logger.info(
                f"[AGENTS] OpenSearch index '{self.index_name}' exists. Validating/Updating mapping..."
            )

            # The key is to only PUT the new properties, allowing OpenSearch to merge
            new_properties = {
                "scope": AGENTS_INDEX_MAPPING["mappings"]["properties"]["scope"],
                "scope_id": AGENTS_INDEX_MAPPING["mappings"]["properties"]["scope_id"],
            }
            try:
                self.client.indices.put_mapping(
                    index=self.index_name, body={"properties": new_properties}
                )
                logger.warning(
                    "🆕 Added 'scope' and 'scope_id' to existing index mapping."
                )
            except exceptions.RequestError as e:
                # This often happens if the index is managed or if a field already exists
                if "MergeMappingException" in str(e):
                    logger.debug(
                        "Mapping merge failed, assuming fields already exist or conflict."
                    )
                else:
                    logger.error(
                        f"Failed to update mapping for index '{self.index_name}': {e}"
                    )

            # Ensure the rest of the mapping is consistent
            validate_index_mapping(self.client, self.index_name, AGENTS_INDEX_MAPPING)
        else:
            self.client.indices.create(index=self.index_name, body=AGENTS_INDEX_MAPPING)
            logger.info(f"[AGENTS] OpenSearch index '{self.index_name}' created.")

    # --- Utility Methods ---
    def _create_doc_id(self, name: str, scope: str, scope_id: Optional[str]) -> str:
        """Creates a composite document ID: <name>:<scope>:<scope_id or 'NULL'>"""
        # FIX: The original was slightly inconsistent. This is the correct, cleaner version:
        scope_id_part = scope_id if scope_id is not None else "NULL"
        return f"{name}:{scope}:{scope_id_part}"

    # ---------------- CRUD with Scoping ----------------

    def save(
        self,
        settings: AgentSettings,
        # FIX 1: Add the required 'tuning' parameter, even if we don't use it directly
        tuning: AgentTuning,
        scope: str = SCOPE_GLOBAL,
        scope_id: Optional[str] = None,
    ) -> None:
        doc_id = self._create_doc_id(settings.id, scope, scope_id)

        # OpenSearch stores the entire document, so we embed scope/scope_id in the saved payload
        # This is a key difference from DuckDB where they are separate columns.

        # 1. Prepare base document body from Pydantic settings
        body: dict = AgentSettingsAdapter.dump_python(
            settings, mode="json", exclude_none=True
        )

        # 2. Add scope fields for indexing/querying
        body["scope"] = scope
        body["scope_id"] = scope_id  # If scope_id is None, it is stored as 'null'

        try:
            self.client.index(index=self.index_name, id=doc_id, body=body)
            logger.info(f"[AGENTS] Agent '{settings.id}' saved (ID: {doc_id})")
        except Exception as e:
            logger.error(
                f"[AGENTS] Failed to save agent '{settings.id}' (ID: {doc_id}): {e}"
            )
            raise

    def save_all(
        self,
        # FIX 2: Correct the type hint to match BaseAgentStore interface
        settings_tuning_list: List[Tuple[AgentSettings, AgentTuning]],
        scope: str = SCOPE_GLOBAL,
        scope_id: Optional[str] = None,
    ) -> None:
        """
        Efficient batch save using the OpenSearch Bulk API.
        """
        if not settings_tuning_list:
            return

        actions = []
        # Iterate over the correct tuple type
        for settings, _ in settings_tuning_list:
            doc_id = self._create_doc_id(settings.id, scope, scope_id)

            # 1. Prepare base document body
            body: dict = AgentSettingsAdapter.dump_python(
                settings, mode="json", exclude_none=True
            )
            # 2. Add scope fields
            body["scope"] = scope
            body["scope_id"] = scope_id

            actions.append({"index": {"_id": doc_id, "_index": self.index_name}})
            actions.append(body)

        try:
            self.client.bulk(actions)
            logger.info(
                f"[AGENTS] Batch saved {len(settings_tuning_list)} agents (Scope: {scope})"
            )
        except Exception as e:
            logger.error(f"[AGENTS] Failed to perform bulk save: {e}")
            raise

    def load_by_scope(
        self,
        scope: str,
        scope_id: Optional[str] = None,
    ) -> List[AgentSettings]:
        """
        Retrieves all persisted agent definitions for a specific scope.
        """
        must_clauses: List[dict] = [{"term": {"scope": scope}}]

        if scope_id is None:
            # Correctly match documents where scope_id is null, using the mapping's 'null_value'
            must_clauses.append({"term": {"scope_id": "null"}})
        else:
            must_clauses.append({"term": {"scope_id": scope_id}})

        query = {"query": {"bool": {"must": must_clauses}}}

        try:
            result = self.client.search(
                index=self.index_name,
                body=query,
                params={"size": 1000},
            )
            docs = [hit["_source"] for hit in result["hits"]["hits"]]

            # Remove transient scope fields before pydantic validation,
            # as they are not part of AgentSettings structure
            for doc in docs:
                doc.pop("scope", None)
                doc.pop("scope_id", None)

            return [AgentSettingsAdapter.validate_python(doc) for doc in docs]
        except Exception as e:
            logger.error(f"[AGENTS] Failed to list agents for scope {scope}: {e}")
            raise

    def load_all_global_scope(self) -> List[AgentSettings]:
        """Backward compatibility: loads all GLOBAL scope agents."""
        return self.load_by_scope(scope=SCOPE_GLOBAL)

    def get(
        self,
        name: str,
        scope: str = SCOPE_GLOBAL,
        scope_id: Optional[str] = None,
    ) -> Optional[AgentSettings]:
        doc_id = self._create_doc_id(name, scope, scope_id)
        try:
            result = self.client.get(index=self.index_name, id=doc_id)
            source = result["_source"]
            source.pop("scope", None)
            source.pop("scope_id", None)
            return AgentSettingsAdapter.validate_python(source)
        except NotFoundError:
            return None
        except Exception as e:
            logger.error(f"[AGENTS] Failed to get agent '{name}' (ID: {doc_id}): {e}")
            raise

    def delete(
        self,
        name: str,
        scope: str = SCOPE_GLOBAL,
        scope_id: Optional[str] = None,
    ) -> None:
        doc_id = self._create_doc_id(name, scope, scope_id)
        try:
            self.client.delete(index=self.index_name, id=doc_id)
            logger.info(f"[AGENTS] Deleted agent '{name}' (ID: {doc_id})")
        except NotFoundError:
            logger.warning(
                f"[AGENTS] Agent '{name}' (ID: {doc_id}) not found for deletion"
            )
        except Exception as e:
            logger.error(
                f"[AGENTS] Failed to delete agent '{name}' (ID: {doc_id}): {e}"
            )
            raise
