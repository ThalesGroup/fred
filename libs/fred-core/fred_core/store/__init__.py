# Copyright Thales 2026
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

from fred_core.store.base_content_store import ContentStore, ObjectInfo
from fred_core.store.content_url_resolver import (
    OBJECT_PROXY_PATH,
    ContentUrlResolver,
    ContentUrlStrategy,
)
from fred_core.store.gcs_content_store import GcsContentStore
from fred_core.store.local_content_store import LocalContentStore
from fred_core.store.minio_content_store import MinioContentStore
from fred_core.store.object_proxy_router import ObjectReader, build_object_proxy_router
from fred_core.store.opensearch_mapping_validator import (
    MappingValidationError,
    ensure_index_mapping,
    validate_index_mapping,
)
from fred_core.store.signed_token import (
    MissingSigningSecretError,
    make_signed_token,
    read_signing_secret,
    verify_signed_token,
)
from fred_core.store.vector_search import VectorSearchHit

__all__ = [
    "OBJECT_PROXY_PATH",
    "ContentStore",
    "ContentUrlResolver",
    "ContentUrlStrategy",
    "GcsContentStore",
    "LocalContentStore",
    "MappingValidationError",
    "MinioContentStore",
    "MissingSigningSecretError",
    "ObjectInfo",
    "ObjectReader",
    "VectorSearchHit",
    "build_object_proxy_router",
    "ensure_index_mapping",
    "make_signed_token",
    "read_signing_secret",
    "validate_index_mapping",
    "verify_signed_token",
]
