from pydantic_settings import BaseSettings
from pydantic import Field
import os

class ContextStoreMinioSettings(BaseSettings):
    minio_endpoint: str = Field(..., validation_alias="MINIO_ENDPOINT")
    minio_access_key: str = Field(..., validation_alias="MINIO_ACCESS_KEY")
    minio_secret_key: str = Field(..., validation_alias="MINIO_SECRET_KEY")
    minio_bucket_name: str = Field(..., validation_alias="MINIO_BUCKET_NAME")
    minio_secure: bool = Field(False, validation_alias="MINIO_SECURE")

    model_config = {
        "env_file": os.getenv("ENV_FILE", None),
        "env_file_encoding": "utf-8",
        "extra": "ignore"
    }