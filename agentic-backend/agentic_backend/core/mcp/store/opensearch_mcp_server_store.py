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

from __future__ import annotations

import logging
from typing import List, Optional

from fred_core import validate_index_mapping
from opensearchpy import NotFoundError, OpenSearch, RequestsHttpConnection
from pydantic import TypeAdapter

from agentic_backend.core.agents.agent_spec import MCPServerConfiguration
from agentic_backend.core.mcp.store.base_mcp_server_store import BaseMcpServerStore

logger = logging.getLogger(__name__)

McpServerAdapter = TypeAdapter(MCPServerConfiguration)

MCP_INDEX_MAPPING = {
    "mappings": {
        "dynamic": False,
        "properties": {
            "id": {"type": "keyword"},
            "name": {"type": "keyword"},
            "description": {"type": "text"},
            "transport": {"type": "keyword"},
            "url": {"type": "keyword"},
            "command": {"type": "keyword"},
            "args": {"type": "keyword"},
            "env": {"type": "object", "enabled": True},
            "enabled": {"type": "boolean"},
            "auth_mode": {"type": "keyword"},
            "sse_read_timeout": {"type": "integer"},
        },
    }
}


class OpenSearchMcpServerStore(BaseMcpServerStore):
    def __init__(
        self,
        host: str,
        index: str,
        username: str,
        password: str,
        secure: bool = False,
        verify_certs: bool = False,
    ):
        self.index_name = index
        self.client = OpenSearch(
            host,
            http_auth=(username, password),
            use_ssl=secure,
            verify_certs=verify_certs,
            connection_class=RequestsHttpConnection,
        )

        if self.client.indices.exists(index=self.index_name):
            validate_index_mapping(self.client, self.index_name, MCP_INDEX_MAPPING)
        else:
            self.client.indices.create(index=self.index_name, body=MCP_INDEX_MAPPING)
            logger.info("[STORE][OPENSEARCH][MCP] Created index %s", self.index_name)

    def save(self, server: MCPServerConfiguration) -> None:
        body = McpServerAdapter.dump_python(
            server, mode="json", exclude_none=True, round_trip=True
        )
        self.client.index(index=self.index_name, id=server.id, body=body)
        logger.debug("[STORE][OPENSEARCH][MCP] Saved server id=%s", server.id)

    def load_all(self) -> List[MCPServerConfiguration]:
        results = self.client.search(
            index=self.index_name,
            body={"query": {"match_all": {}}},
            params={"size": 1000},
        )
        out: List[MCPServerConfiguration] = []
        for hit in results.get("hits", {}).get("hits", []):
            source = hit.get("_source", {})
            try:
                out.append(McpServerAdapter.validate_python(source))
            except Exception:
                logger.exception(
                    "[STORE][OPENSEARCH][MCP] Failed to parse server payload for id=%s",
                    hit.get("_id"),
                )
        return out

    def get(self, server_id: str) -> Optional[MCPServerConfiguration]:
        try:
            resp = self.client.get(index=self.index_name, id=server_id)
            return McpServerAdapter.validate_python(resp.get("_source", {}))
        except NotFoundError:
            return None
        except Exception:
            logger.exception(
                "[STORE][OPENSEARCH][MCP] Failed to retrieve server id=%s", server_id
            )
            return None

    def delete(self, server_id: str) -> None:
        try:
            self.client.delete(index=self.index_name, id=server_id)
            logger.info("[STORE][OPENSEARCH][MCP] Deleted server id=%s", server_id)
        except NotFoundError:
            logger.warning("[STORE][OPENSEARCH][MCP] Server id=%s not found", server_id)
        except Exception:
            logger.exception(
                "[STORE][OPENSEARCH][MCP] Failed to delete server id=%s", server_id
            )
