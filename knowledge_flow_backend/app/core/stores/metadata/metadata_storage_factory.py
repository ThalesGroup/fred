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

from app.application_context import ApplicationContext
from app.config.metadata_store_local_settings import MetadataStoreLocalSettings
from app.config.opensearch_settings import OpenSearchSettings
from app.common.utils import validate_settings_or_exit
from pathlib import Path

from app.core.stores.base_metadata_store import BaseMetadataStore
from app.core.stores.metadata.local_metadata_store import LocalMetadataStore
from app.core.stores.metadata.opensearch_metadata_store import OpenSearchMetadataStore



def get_metadata_store() -> BaseMetadataStore:
    """
    Factory function to create a metadata store instance based on the configuration.
    As of now, it supports local and OpenSearch metadata storage.
    Returns:
        BaseMetadataStore: An instance of the metadata store.
    """
    # Get the metadata storage configuration from the application context
    config = ApplicationContext.get_instance().get_config().metadata_storage

    if config.type == "local":
        settings = MetadataStoreLocalSettings()
        return LocalMetadataStore(Path(settings.root_path).expanduser())
    elif config.type == "opensearch":
        settings = validate_settings_or_exit(OpenSearchSettings, "OpenSearch Settings")
        return OpenSearchMetadataStore(
            host=settings.opensearch_host,
            username=settings.opensearch_user,
            password=settings.opensearch_password,
            secure=settings.opensearch_secure,
            verify_certs=settings.opensearch_verify_certs,
            vector_index_name=settings.opensearch_vector_index,
            metadata_index_name=settings.opensearch_metadata_index,
        )
    else:
        raise ValueError(f"Unsupported metadata storage backend: {config.type}")
