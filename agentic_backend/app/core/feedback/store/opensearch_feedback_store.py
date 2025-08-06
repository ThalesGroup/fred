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

from opensearchpy import (
    OpenSearch,
    NotFoundError,
    ConflictError,
    RequestsHttpConnection,
)

from app.core.feedback.structures import FeedbackRecord
from app.core.feedback.store.base_feedback_store import BaseFeedbackStore

logger = logging.getLogger(__name__)

# ==============================================================================
# FEEDBACK_INDEX_MAPPING
# ==============================================================================

FEEDBACK_INDEX_MAPPING = {
    "mappings": {
        "properties": {
            "id": {"type": "keyword"},
            "session_id": {"type": "keyword"},
            "message_id": {"type": "keyword"},
            "agent_name": {"type": "keyword"},
            "rating": {"type": "integer"},
            "comment": {"type": "text"},
            "created_at": {"type": "date"},
            "user_id": {"type": "keyword"},
        }
    }
}


class OpenSearchFeedbackStore(BaseFeedbackStore):
    """
    OpenSearch implementation of BaseFeedbackStore for FeedbackRecord.
    Automatically creates the index if it doesn't exist.
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
            self.client.indices.create(
                index=self.index_name, body=FEEDBACK_INDEX_MAPPING
            )
            logger.info(f"[FEEDBACK] OpenSearch index '{self.index_name}' created.")
        else:
            logger.info(
                f"[FEEDBACK] OpenSearch index '{self.index_name}' already exists."
            )

    def list(self) -> List[FeedbackRecord]:
        try:
            response = self.client.search(
                index=self.index_name,
                body={"query": {"match_all": {}}},
                params={"size": 10000},
            )
            return [
                FeedbackRecord(**hit["_source"]) for hit in response["hits"]["hits"]
            ]
        except Exception as e:
            logger.error(f"[FEEDBACK] Failed to list feedback entries: {e}")
            raise

    def get(self, feedback_id: str) -> Optional[FeedbackRecord]:
        try:
            response = self.client.get(index=self.index_name, id=feedback_id)
            return FeedbackRecord(**response["_source"])
        except NotFoundError:
            return None
        except Exception as e:
            logger.error(f"[FEEDBACK] Failed to get feedback '{feedback_id}': {e}")
            raise

    def save(self, feedback: FeedbackRecord) -> None:
        try:
            self.client.index(
                index=self.index_name,
                id=feedback.id,
                body=feedback.model_dump(mode="json"),
            )
            logger.info(f"[FEEDBACK] Saved feedback entry '{feedback.id}'")
        except ConflictError:
            logger.warning(f"[FEEDBACK] Conflict saving feedback entry '{feedback.id}'")
            raise
        except Exception as e:
            logger.error(
                f"[FEEDBACK] Failed to save feedback entry '{feedback.id}': {e}"
            )
            raise

    def delete(self, feedback_id: str) -> None:
        try:
            self.client.delete(index=self.index_name, id=feedback_id)
            logger.info(f"[FEEDBACK] Deleted feedback entry '{feedback_id}'")
        except NotFoundError:
            logger.warning(
                f"[FEEDBACK] Feedback entry '{feedback_id}' not found for deletion"
            )
        except Exception as e:
            logger.error(
                f"[FEEDBACK] Failed to delete feedback entry '{feedback_id}': {e}"
            )
            raise
