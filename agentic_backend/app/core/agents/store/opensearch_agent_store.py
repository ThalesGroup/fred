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


import logging
from typing import List, Optional

from opensearchpy import OpenSearch, NotFoundError, RequestsHttpConnection

from app.common.structures import AgentSettings
from app.core.agents.store.base_agent_store import BaseAgentStore

logger = logging.getLogger(__name__)

AGENTS_INDEX_MAPPING = {
    "mappings": {
        "properties": {
            "name": {"type": "keyword"},
            "type": {"type": "keyword"},
            "enabled": {"type": "boolean"},
            "categories": {"type": "keyword"},
            "settings": {"type": "object", "enabled": True},
            "model": {"type": "object", "enabled": True},
            "tag": {"type": "keyword"},
            "mcp_servers": {"type": "nested"},
            "max_steps": {"type": "integer"},
            "description": {"type": "text"},
            "base_prompt": {"type": "text"},
            "nickname": {"type": "text"},
            "role": {"type": "text"},
            "icon": {"type": "keyword"},
        }
    }
}


class OpenSearchAgentStore(BaseAgentStore):
    """
    OpenSearch implementation of BaseAgentStore.
    Each agent is stored under its name as document ID.
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
            logger.info(f"[AGENTS] OpenSearch index '{self.index_name}' already exists.")

    def save(self, settings: AgentSettings) -> None:
        try:
            self.client.index(
                index=self.index_name,
                id=settings.name,
                body=settings.model_dump(mode="json"),
            )
            logger.info(f"[AGENTS] Agent '{settings.name}' saved")
        except Exception as e:
            logger.error(f"[AGENTS] Failed to save agent '{settings.name}': {e}")
            raise

    def load_all(self) -> List[AgentSettings]:
        try:
            result = self.client.search(
                index=self.index_name,
                body={"query": {"match_all": {}}},
                params={"size": 1000},
            )
            return [AgentSettings(**hit["_source"]) for hit in result["hits"]["hits"]]
        except Exception as e:
            logger.error(f"[AGENTS] Failed to list agents: {e}")
            raise

    def get(self, name: str) -> Optional[AgentSettings]:
        try:
            result = self.client.get(index=self.index_name, id=name)
            return AgentSettings(**result["_source"])
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
