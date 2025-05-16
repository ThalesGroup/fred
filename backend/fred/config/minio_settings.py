from pydantic_settings import BaseSettings
from pydantic import Field
import os
import logging
from typing import ClassVar

logger = logging.getLogger(__name__)

class MinioSettings(BaseSettings):
    """
    Settings for MinIO integration, sourced from environment variables.
    """
    # Variables d'environnement avec validation
    minio_endpoint: str = Field("localhost:9000", validation_alias="MINIO_ENDPOINT")
    minio_access_key: str = Field("minioadmin", validation_alias="MINIO_ACCESS_KEY")
    minio_secret_key: str = Field("minioadmin", validation_alias="MINIO_SECRET_KEY")
    minio_bucket_name: str = Field("fred-storage", validation_alias="MINIO_BUCKET_NAME")
    minio_secure: bool = Field(False, validation_alias="MINIO_SECURE")
    minio_bucket_context_name: str = Field("agent-contexts", validation_alias="MINIO_BUCKET_CONTEXT_NAME")
    
    # Configuration du modèle
    model_config = {
        "env_file": os.getenv("ENV_FILE", None),
        "env_file_encoding": "utf-8",
        "extra": "ignore"
    }


# Default singleton instance
minio_settings = MinioSettings()
