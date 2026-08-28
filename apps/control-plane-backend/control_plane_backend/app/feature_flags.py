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

"""Small, backend-authoritative guards for frontend-visible feature flags."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import HTTPException, Request

from control_plane_backend.app.dependencies import get_application_configuration
from control_plane_backend.config.models import Configuration, FrontendFeatureFlags


def _validate_feature_name(feature_name: str) -> None:
    if feature_name not in FrontendFeatureFlags.model_fields:
        raise ValueError(f"Unknown frontend feature flag {feature_name!r}.")


def is_feature_enabled(configuration: Configuration, feature_name: str) -> bool:
    """Read one typed deployment feature flag from control-plane configuration."""

    _validate_feature_name(feature_name)
    return getattr(configuration.platform.frontend.feature_flags, feature_name) is True


def require_feature_enabled(feature_name: str) -> Callable[[Request], None]:
    """Build a FastAPI guard that makes a disabled feature look unavailable."""

    _validate_feature_name(feature_name)

    def guard(request: Request) -> None:
        configuration = get_application_configuration(request)
        if not is_feature_enabled(configuration, feature_name):
            # A deployment-disabled feature is absent, not unauthorized or
            # temporarily unhealthy. Keep the response generic so the guard
            # does not advertise hidden feature metadata.
            raise HTTPException(status_code=404, detail="Not Found")

    return guard
