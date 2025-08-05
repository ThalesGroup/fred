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
from typing import List

from opensearchpy import OpenSearch, NotFoundError, ConflictError, RequestsHttpConnection

from app.core.stores.prompts.base_prompt_store import (
    BasePromptStore,
    PromptAlreadyExistsError,
    PromptNotFoundError,
)
from app.features.prompts.structure import Prompt

logger = logging.getLogger(__name__)

PROMPTS_INDEX_MAPPING = {
    "mappings": {
        "properties": {
            "id": {"type": "keyword"},
            "name": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
            },
            "content": {"type": "text"},
            "description": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
            },
            "tags": {"type": "keyword"},
            "owner_id": {"type": "keyword"},
            "created_at": {"type": "date"},
            "updated_at": {"type": "date"},
        }
    }
}


class OpenSearchPromptStore(BasePromptStore):
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
            self.client.indices.create(index=self.index_name, body=PROMPTS_INDEX_MAPPING)
            logger.info(f"[PROMPTS] OpenSearch index '{self.index_name}' created.")
        else:
            logger.info(f"[PROMPTS] OpenSearch index '{self.index_name}' already exists.")

    def list_prompts_for_user(self, user: str) -> List[Prompt]:
        try:
            response = self.client.search(index=self.index_name, body={"query": {"term": {"owner_id": user}}},  params={"size": 10000})
            return [Prompt(**hit["_source"]) for hit in response["hits"]["hits"]]
        except Exception as e:
            logger.error(f"[PROMPTS] Failed to list prompts for user '{user}': {e}")
            raise

    def get_prompt_by_id(self, prompt_id: str) -> Prompt:
        try:
            response = self.client.get(index=self.index_name, id=prompt_id)
            return Prompt(**response["_source"])
        except NotFoundError:
            raise PromptNotFoundError(f"Prompt with id '{prompt_id}' not found.")
        except Exception as e:
            logger.error(f"[PROMPTS] Failed to get prompt '{prompt_id}': {e}")
            raise

    def create_prompt(self, prompt: Prompt) -> Prompt:
        try:
            self.client.index(
                index=self.index_name,
                id=prompt.id,
                body=prompt.model_dump(mode="json"),
            )
            logger.info(f"[PROMPTS] Created prompt '{prompt.id}'")
            return prompt
        except ConflictError:
            raise PromptAlreadyExistsError(f"Prompt '{prompt.id}' already exists.")
        except Exception as e:
            logger.error(f"[PROMPTS] Failed to create prompt '{prompt.id}': {e}")
            raise

    def update_prompt(self, prompt_id: str, prompt: Prompt) -> Prompt:
        try:
            self.get_prompt_by_id(prompt_id)  # ensure exists
            self.client.index(
                index=self.index_name,
                id=prompt_id,
                body=prompt.model_dump(mode="json"),
            )
            logger.info(f"[PROMPTS] Updated prompt '{prompt_id}'")
            return prompt
        except PromptNotFoundError:
            raise
        except Exception as e:
            logger.error(f"[PROMPTS] Failed to update prompt '{prompt_id}': {e}")
            raise

    def delete_prompt(self, prompt_id: str) -> None:
        try:
            self.client.delete(index=self.index_name, id=prompt_id)
            logger.info(f"[PROMPTS] Deleted prompt '{prompt_id}'")
        except NotFoundError:
            raise PromptNotFoundError(f"Prompt '{prompt_id}' not found.")
        except Exception as e:
            logger.error(f"[PROMPTS] Failed to delete prompt '{prompt_id}': {e}")
            raise

    def get_prompt_in_tag(self, tag_id: str) -> List[Prompt]:
        """
        Retrieve all prompts associated with a specific tag.
        Raises:
            PromptNotFoundError: If no prompts are found for the tag.
        """
        try:
            query = {"query": {"bool": {"filter": {"term": {"tags": tag_id}}}}}
            response = self.client.search(index=self.index_name, body=query, params={"size": 10000})
            if not response["hits"]["hits"]:
                raise PromptNotFoundError(f"No prompts found for tag '{tag_id}'")
            return [Prompt(**hit["_source"]) for hit in response["hits"]["hits"]]

        except PromptNotFoundError:
            # Rethrow silently without logging
            raise

        except Exception as e:
            logger.error(f"[PROMPTS] Failed to get prompts for tag '{tag_id}': {e}")
            raise
