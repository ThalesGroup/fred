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

"""
What a Knowledge Base pod reads from its environment.

Fred neither reads nor knows this — a KB's deployment is none of Fred's
business — but a portable contract that leaves a third party guessing variable
names is not portable, so the SDK owns and documents it here.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

CONTROL_PLANE_URL_ENV = "FRED_CONTROL_PLANE_URL"
KEYCLOAK_REALM_URL_ENV = "FRED_KEYCLOAK_REALM_URL"
PROVIDER_ID_ENV = "FRED_KB_PROVIDER_ID"
CLIENT_ID_ENV = "FRED_KB_CLIENT_ID"
CLIENT_SECRET_ENV = "FRED_KB_CLIENT_SECRET"  # nosec B105 - a variable name, not a value
TEMPORAL_HOST_ENV = "FRED_TEMPORAL_HOST"
TEMPORAL_NAMESPACE_ENV = "FRED_TEMPORAL_NAMESPACE"

DEFAULT_TEMPORAL_NAMESPACE = "default"


class MissingPodEnvironment(RuntimeError):
    """Raised when a pod starts without the variables its contract requires."""


@dataclass(frozen=True)
class PodEnvironment:
    """The deployment values a KB pod needs to reach Fred and Temporal.

    `provider_id` names the namespace this image owns in Fred's catalog — the
    Knowledge Base counterpart of an agent pod's `runtime_id`. Every definition
    it publishes lives under it, and Fred binds it to this pod's client on the
    first publication, so no other workload can write there.
    """

    control_plane_url: str
    provider_id: str
    client_id: str
    keycloak_realm_url: str = ""
    temporal_host: str = ""
    temporal_namespace: str = DEFAULT_TEMPORAL_NAMESPACE

    @property
    def authenticated(self) -> bool:
        """Whether this pod mints a token for its calls to Fred.

        False only when no client secret is set, which mirrors a deployment
        running with `security.user.enabled: false`. A Fred that does check
        tokens rejects such a pod, so this cannot pass unnoticed anywhere it
        matters.
        """
        return bool(self.keycloak_realm_url)

    @classmethod
    def from_env(cls, *, require_temporal: bool) -> "PodEnvironment":
        """Read the environment, naming everything missing in one error.

        `publish` needs Fred only; serving runs also needs Temporal — failing on
        the whole set either way would make the publish Job depend on a worker
        it never starts. Keycloak is required only when a client secret is set,
        so a local stack with authentication off needs neither.
        """
        required = [CONTROL_PLANE_URL_ENV, PROVIDER_ID_ENV, CLIENT_ID_ENV]
        if os.getenv(CLIENT_SECRET_ENV):
            required.append(KEYCLOAK_REALM_URL_ENV)
        if require_temporal:
            required.append(TEMPORAL_HOST_ENV)

        missing = [name for name in required if not os.getenv(name)]
        if missing:
            raise MissingPodEnvironment(
                "Missing Knowledge Base pod environment: " + ", ".join(missing)
            )

        return cls(
            control_plane_url=os.environ[CONTROL_PLANE_URL_ENV].rstrip("/"),
            provider_id=os.environ[PROVIDER_ID_ENV],
            client_id=os.environ[CLIENT_ID_ENV],
            keycloak_realm_url=os.getenv(KEYCLOAK_REALM_URL_ENV, "").rstrip("/"),
            temporal_host=os.getenv(TEMPORAL_HOST_ENV, ""),
            temporal_namespace=os.getenv(
                TEMPORAL_NAMESPACE_ENV, DEFAULT_TEMPORAL_NAMESPACE
            ),
        )
