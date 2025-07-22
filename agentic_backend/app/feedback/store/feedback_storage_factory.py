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
import logging
from pathlib import Path
from app.main_utils import validate_settings_or_exit
from app.config.feedback_store_local_settings import FeedbackStoreLocalSettings
from app.config.feedback_store_search_engine_settings import FeedbackStoreSearchEngineSettings
from app.feedback.feedback_service import FeedbackService
from app.feedback.store.local_feedback_store import LocalFeedbackStore
from app.feedback.store.search_engine_feedback_store import SearchEngineFeedbackStore

logger = logging.getLogger(__name__)

def _create_feedback_service():
    """
    Factory function to create a feedback service based on the configured storage backend.
    Supports 'local' and 'opensearch'.
    """
    from app.application_context import get_configuration
    config = get_configuration().feedback_storage

    if config.type == "local":
        settings = validate_settings_or_exit(FeedbackStoreLocalSettings)
        store = LocalFeedbackStore(Path(settings.root_path).expanduser())
    elif config.type == "opensearch":
        settings = validate_settings_or_exit(FeedbackStoreSearchEngineSettings)
        store = SearchEngineFeedbackStore(
            host=settings.search_engine_host,
            username=settings.search_engine_user,
            password=settings.search_engine_password,
            secure=settings.search_engine_secure,
            verify_certs=settings.search_engine_verify_certs,
            index_name=settings.search_engine_feedback_index
        )
    else:
        raise ValueError(f"Unsupported feedback storage backend: {config.type}")

    return FeedbackService(store)
