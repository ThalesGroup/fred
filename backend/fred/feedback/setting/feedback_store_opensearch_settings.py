import logging
from pydantic_settings import BaseSettings
from pydantic import Field
import os

logger = logging.getLogger(__name__)

class FeedbackStoreOpenSearchSettings(BaseSettings):
    """
    Configuration for storing feedback in OpenSearch.
    """

    opensearch_host: str = Field(..., validation_alias="OPENSEARCH_HOST")
    opensearch_user: str = Field(..., validation_alias="OPENSEARCH_USER")
    opensearch_password: str = Field(..., validation_alias="OPENSEARCH_PASSWORD")
    opensearch_secure: bool = Field(False, validation_alias="OPENSEARCH_SECURE")
    opensearch_verify_certs: bool = Field(False, validation_alias="OPENSEARCH_VERIFY_CERTS")
    opensearch_feedback_index: str = Field(..., validation_alias="OPENSEARCH_FEEDBACK_INDEX")

    model_config = {
        "env_file": os.getenv("ENV_FILE", ".env"),
        "env_file_encoding": "utf-8",
        "extra": "ignore"
    }

    @classmethod
    def validate_or_exit(cls):
        try:
            return cls()
        except Exception as e:
            logger.critical("❌ Invalid OpenSearch feedback settings:\n%s", e)
            raise SystemExit(1)
