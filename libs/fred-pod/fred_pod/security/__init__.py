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

"""Identity: who a pod is to Fred, and who a caller is to a pod."""

from fred_pod.security.backend_to_backend_auth import (
    M2MAuthConfig,
    M2MBearerAuth,
    M2MTokenProvider,
    make_m2m_asgi_client,
)
from fred_pod.security.structure import (
    LOCAL_DEV_CLIENT_ID,
    SERVICE_AGENT_ROLE,
    KeycloakUser,
    M2MSecurity,
    OpenFgaRebacConfig,
    RebacBaseConfig,
    RebacConfiguration,
    SecurityConfiguration,
    UserSecurity,
    is_service_agent,
)

__all__ = [
    "LOCAL_DEV_CLIENT_ID",
    "SERVICE_AGENT_ROLE",
    "KeycloakUser",
    "M2MAuthConfig",
    "M2MBearerAuth",
    "M2MSecurity",
    "M2MTokenProvider",
    "OpenFgaRebacConfig",
    "RebacBaseConfig",
    "RebacConfiguration",
    "SecurityConfiguration",
    "UserSecurity",
    "is_service_agent",
    "make_m2m_asgi_client",
]
