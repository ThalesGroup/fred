from pathlib import Path
from context.store.base_context_store import BaseContextStore
from context.store.local_context_store import LocalContextStore
from context.store.minio_context_store import MinIOContextStore
from context.setting.context_store_local_settings import ContextStoreLocalSettings
from context.setting.context_store_minio_settings import ContextStoreMinioSettings
from fred.application_context import get_configuration
from minio import Minio


def get_context_store() -> BaseContextStore:
    """
    Factory function to create a context store instance based on the configuration.
    Supports 'local' and 'minio' backends.
    """
    config = get_configuration().context_storage

    if config.type == "local":
        settings = ContextStoreLocalSettings()
        return LocalContextStore(Path(settings.root_path).expanduser())

    elif config.type == "minio":
        settings = ContextStoreMinioSettings()
        minio_client = Minio(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure
        )
        return MinIOContextStore(minio_client, bucket_name=settings.minio_bucket_name)

    else:
        raise ValueError(f"Unsupported context storage backend: {config}")
