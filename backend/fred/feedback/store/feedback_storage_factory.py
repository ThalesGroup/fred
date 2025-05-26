import os
import logging
from pathlib import Path
from main_utils import validate_settings_or_exit
from config.feedback_store_local_settings import FeedbackStoreLocalSettings
from config.feedback_store_opensearch_settings import FeedbackStoreOpenSearchSettings
from feedback.feedback_service import FeedbackService
from feedback.store.local_feedback_store import LocalFeedbackStore
from feedback.store.opensearch_feedback_store import OpenSearchFeedbackStore

logger = logging.getLogger(__name__)

def _create_feedback_service():
    """
    Factory function to create a feedback service based on the configured storage backend.
    Supports 'local' and 'opensearch'.
    """
    from fred.application_context import get_configuration
    config = get_configuration().feedback_storage

    if config.type == "local":
        settings = validate_settings_or_exit(FeedbackStoreLocalSettings)
        store = LocalFeedbackStore(Path(settings.root_path).expanduser())
    elif config.type == "opensearch":
        settings = validate_settings_or_exit(FeedbackStoreOpenSearchSettings)
        store = OpenSearchFeedbackStore(
            host=settings.opensearch_host,
            username=settings.opensearch_user,
            password=settings.opensearch_password,
            secure=settings.opensearch_secure,
            verify_certs=settings.opensearch_verify_certs,
            index_name=settings.opensearch_feedback_index
        )
    else:
        raise ValueError(f"Unsupported feedback storage backend: {config.type}")

    return FeedbackService(store)
