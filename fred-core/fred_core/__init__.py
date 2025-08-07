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

from fred_core.common.structures import OpenSearchStorageConfig
from fred_core.common.utils import raise_internal_error
from fred_core.security.keycloak import get_current_user, initialize_keycloak
from fred_core.security.structure import KeycloakUser, SecurityConfiguration
from fred_core.store.filters import generate_filter_model, BaseFilter
from fred_core.store.filter_processors import FilterProcessor, OpenSearchFilterProcessor, DuckDBFilterProcessor
from fred_core.store.local_json_store import (
    BaseModelWithId,
    LocalJsonStore,
    ResourceAlreadyExistsError,
    ResourceNotFoundError,
)

__all__ = [
    "OpenSearchStorageConfig",
    "raise_internal_error",
    "get_current_user",
    "initialize_keycloak",
    "KeycloakUser",
    "SecurityConfiguration",
    "generate_filter_model",
    "BaseFilter",
    "FilterProcessor",
    "OpenSearchFilterProcessor",
    "DuckDBFilterProcessor",
    "BaseModelWithId",
    "LocalJsonStore",
    "ResourceAlreadyExistsError",
    "ResourceNotFoundError",
]
