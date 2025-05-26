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
        "extra": "ignore"
    }