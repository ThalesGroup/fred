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

from .catalog import (
    ModelCatalog,
    load_model_catalog,
    load_model_routing_policy_from_catalog,
)
from .contracts import (
    FrozenModel,
    MatchValue,
    ModelCapability,
    ModelProfile,
    ModelRouteMatch,
    ModelRouteRule,
    ModelRoutingPolicy,
    ModelSelection,
    ModelSelectionRequest,
    ModelSelectionSource,
)
from .provider import FredCoreModelProvider, RoutedChatModelFactory
from .resolver import ModelRoutingResolver

__all__ = [
    "FredCoreModelProvider",
    "FrozenModel",
    "MatchValue",
    "ModelCapability",
    "ModelCatalog",
    "ModelProfile",
    "ModelRouteMatch",
    "ModelRouteRule",
    "ModelRoutingPolicy",
    "ModelRoutingResolver",
    "ModelSelection",
    "ModelSelectionRequest",
    "ModelSelectionSource",
    "RoutedChatModelFactory",
    "load_model_catalog",
    "load_model_routing_policy_from_catalog",
]
