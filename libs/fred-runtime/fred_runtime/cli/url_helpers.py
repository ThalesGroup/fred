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

from __future__ import annotations

import os
from urllib.parse import urlparse, urlunparse

from fred_core.cli.auth import default_configuration_file, load_configuration_yaml

from .pod_client import DEFAULT_AGENT_POD_BASE_URL


def default_agent_pod_base_url() -> str:
    """
    Resolve the default pod base URL for the chat client.

    Resolution order:
    1. `FRED_AGENT_POD_URL` environment variable (explicit override).
    2. `app.port` and `app.base_url` from the pod's `configuration.yaml`.
    3. Built-in fallback: `http://127.0.0.1:8000/api/v1`.
    """
    explicit = os.getenv("FRED_AGENT_POD_URL")
    if explicit:
        return normalize_base_url(explicit)

    payload = load_configuration_yaml(default_configuration_file())
    if isinstance(payload, dict):
        app_section = payload.get("app")
        if isinstance(app_section, dict):
            port = app_section.get("port", 8000)
            base = str(app_section.get("base_url", "/api/v1")).rstrip("/")
            return normalize_base_url(f"http://127.0.0.1:{port}{base}")

    return normalize_base_url(DEFAULT_AGENT_POD_BASE_URL)


def default_agent_metrics_url(*, base_url: str | None = None) -> str | None:
    """
    Resolve the default Prometheus metrics URL for the target pod.

    Resolution order:
    1. `FRED_AGENT_METRICS_URL` environment variable (explicit override).
    2. `app.metrics_port` and optional `app.metrics_address` from `configuration.yaml`.
    3. `None` when no metrics configuration is available.
    """
    explicit = os.getenv("FRED_AGENT_METRICS_URL")
    if explicit:
        return explicit.rstrip("/")

    payload = load_configuration_yaml(default_configuration_file())
    if not isinstance(payload, dict):
        return None
    app_section = payload.get("app")
    if not isinstance(app_section, dict):
        return None

    metrics_port = app_section.get("metrics_port")
    if metrics_port in (None, ""):
        return None

    try:
        port = int(metrics_port)
    except (TypeError, ValueError):
        return None

    parsed_base = urlparse(base_url or default_agent_pod_base_url())
    fallback_host = parsed_base.hostname or "127.0.0.1"
    scheme = parsed_base.scheme or "http"
    raw_host = (
        str(app_section.get("metrics_address", fallback_host)).strip() or fallback_host
    )
    host = fallback_host if raw_host in {"0.0.0.0", "::", "[::]"} else raw_host  # nosec B104 - rewrite wildcard bind address to the active target host for local scraping
    return urlunparse((scheme, f"{host}:{port}", "/metrics", "", "", ""))


def normalize_base_url(base_url: str) -> str:
    """Normalize one pod base URL: strip trailing slash."""
    cleaned = base_url.strip()
    if not cleaned:
        raise ValueError("base_url cannot be empty.")
    return cleaned.rstrip("/")
