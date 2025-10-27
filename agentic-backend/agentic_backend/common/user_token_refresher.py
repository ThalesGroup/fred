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

import logging
import time
from typing import Any, Dict

import requests

logger = logging.getLogger(__name__)


def refresh_user_access_token_from_keycloak(
    keycloak_url: str, client_id: str, refresh_token: str
) -> Dict[str, Any]:
    """Exchanges a user's refresh token for a new access token and refresh token pair."""

    token_url = f"{keycloak_url.rstrip('/')}/protocol/openid-connect/token"

    form = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "refresh_token": refresh_token,
    }

    try:
        r = requests.post(token_url, data=form, timeout=10)
        r.raise_for_status()  # Raise HTTPError on 4xx/5xx responses
    except requests.exceptions.HTTPError as e:
        error_details = {
            "error": e.response.text[:200]
            if e.response is not None
            else "Unknown error"
        }
        logger.error(
            "Keycloak refresh request failed (status=%s): %s",
            e.response.status_code if e.response is not None else "N/A",
            error_details,
        )
        raise RuntimeError(f"Token refresh failed: {error_details['error']}") from e

    payload = r.json()

    # Calculate expiry timestamp (optional but good practice)
    expires_in = int(payload.get("expires_in", 300))
    payload["expires_at_timestamp"] = time.time() + max(0, expires_in - 5)

    return payload
