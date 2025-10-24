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

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable, Dict

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.application_context import get_app_context

logger = logging.getLogger(__name__)


def _session_with_retries(allowed_methods: frozenset) -> requests.Session:
    """Creates a requests session configured with retries for transient errors."""
    s = requests.Session()
    retry = Retry(
        total=2,
        backoff_factor=0.3,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=allowed_methods,
        raise_on_status=False,
    )
    s.mount("http://", HTTPAdapter(max_retries=retry))
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


TokenRefreshCallback = Callable[[], str]

if TYPE_CHECKING:
    from app.core.agents.agent_flow import AgentFlow


class KfBaseClient:
    """
    Base client providing secured, retrying access to any Fred/Knowledge Flow backend service.

    This client is designed for **end-user identity propagation** and requires an
    `access_token` to be explicitly passed for all requests. M2M authentication is removed.
    """

    def __init__(self, allowed_methods: frozenset, agent: "AgentFlow"):
        ctx = get_app_context()
        self.agent = agent
        # Base URL: ensure no trailing slash so path concatenation is safe
        self.base_url = ctx.get_knowledge_flow_base_url().rstrip("/")

        tcfg = ctx.configuration.ai.timeout
        connect_t = float(tcfg.connect or 5)
        read_t = float(tcfg.read or 30)  # Defaulting to a longer read for streams
        self.timeout: float | tuple[float, float] = (connect_t, read_t)

        # Session setup uses the specific methods required by the derived class.
        # Note: session.auth is NOT set, as we rely solely on the request-time header.
        self.session = _session_with_retries(allowed_methods)

        # M2M token refresh logic is removed, as we don't use M2M tokens.
        # self._on_auth_refresh = None # (or just don't define it)

    def _execute_authenticated_request(
        self, method: str, path: str, **kwargs: Any
    ) -> requests.Response:
        """
        Executes a single authenticated request attempt. Requires `access_token`.
        This is the core execution logic, replacing _request_once.
        """
        access_token = self.agent.runtime_context.access_token
        if not access_token:
            raise ValueError(
                "Cannot make an authenticated request: 'access_token' must be provided to KfBaseClient."
            )

        url = f"{self.base_url}{path}"
        headers: Dict[str, str] = kwargs.pop("headers", {})

        # Set the Bearer header with the required user token.
        headers["Authorization"] = f"Bearer {access_token}"

        # Network retries (for 5xx, 429) are handled by self.session automatically.
        return self.session.request(
            method, url, timeout=self.timeout, headers=headers, **kwargs
        )

    def _request_with_token_refresh(
        self, method: str, path: str, **kwargs: Any
    ) -> requests.Response:
        """
        Executes a request, handling token expiration (401) via callback and retry.
        """

        for attempt in range(2):
            try:
                # Use the existing _request_with_auth_retry for the network retry part
                r = self._execute_authenticated_request(
                    method=method, path=path, **kwargs
                )

                r.raise_for_status()  # Raise exception on 4xx/5xx
                return r  # Success!

            except requests.exceptions.HTTPError as e:
                # 1. Check for 401 and if a callback is available on the first attempt
                if (
                    e.response.status_code == 401
                    and attempt == 0
                    and self.agent.refresh_user_access_token is not None
                ):
                    logger.warning(
                        "Received 401 Unauthorized on %s %s. Attempting token refresh via callback...",
                        method,
                        path,
                    )

                    try:
                        # 2. Call the provided refresh function
                        self.agent.refresh_user_access_token()
                        logger.info("Token refresh successful. Retrying request.")
                        continue  # Skip to next iteration (attempt = 1)

                    except Exception as refresh_err:
                        logger.error(
                            f"FATAL: Token refresh failed. Cannot retry: {refresh_err}"
                        )
                        raise e  # Re-raise the original 401 error

                # 3. Re-raise if not a 401, no callback, or second attempt
                raise e

        # Should be unreachable
        raise Exception("Unhandled HTTP error after all retries.")
