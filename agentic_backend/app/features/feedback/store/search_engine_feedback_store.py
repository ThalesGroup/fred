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

from opensearchpy import OpenSearch as SearchEngine, exceptions
from app.features.feedback.store.base_feedback_store import BaseFeedbackStore
import logging
import json

logger = logging.getLogger(__name__)

class SearchEngineFeedbackStore(BaseFeedbackStore):
    def __init__(self, host: str, port: int, index: str, user: str, password: str, use_ssl: bool = False):
        self.index = index
        self.client = SearchEngine(
            hosts=[{"host": host, "port": port}],
            http_auth=(user, password),
            use_ssl=use_ssl,
            verify_certs=use_ssl
        )

        if not self.client.indices.exists(index=self.index):
            self.client.indices.create(index=self.index)
            logger.info(f"📦 Created SearchEngine index: {self.index}")

    def get_feedback(self, key: str) -> str | None:
        try:
            res = self.client.get(index=self.index, id=key)
            return json.dumps(res["_source"])
        except exceptions.NotFoundError:
            logger.warning(f"⚠️ No feedback found for key: {key}")
            return None
        except Exception as e:
            logger.error(f"❌ Error retrieving feedback: {e}")
            raise

    def set_feedback(self, key: str, feedback: str) -> None:
        try:
            self.client.index(index=self.index, id=key, body=json.loads(feedback))
            logger.info(f"💾 Feedback stored with key: {key}")
        except Exception as e:
            logger.error(f"❌ Failed to store feedback: {e}")
            raise

    def delete_feedback(self, key: str) -> None:
        try:
            self.client.delete(index=self.index, id=key)
            logger.info(f"🗑️ Deleted feedback with key: {key}")
        except exceptions.NotFoundError:
            logger.warning(f"⚠️ Tried to delete non-existent feedback key: {key}")
        except Exception as e:
            logger.error(f"❌ Failed to delete feedback: {e}")
            raise
