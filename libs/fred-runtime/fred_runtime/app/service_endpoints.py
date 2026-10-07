# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Supply catalog service addresses from the pod's existing configuration."""

from urllib.parse import urlsplit

from fred_sdk.contracts.services import FredService, ServiceEndpointsPort

from .config import AgentPodConfig


class ConfiguredServiceEndpoints(ServiceEndpointsPort):
    """Read outbound addresses, including ports and API prefixes, at pod boot."""

    def __init__(self, config: AgentPodConfig) -> None:
        self._urls = {
            FredService.KNOWLEDGE_FLOW: config.ai.knowledge_flow_url,
            FredService.CONTROL_PLANE: config.platform.control_plane_url,
        }

    def get_base_url(self, service: FredService) -> str:
        url = self._urls.get(service)
        if not url:
            raise ValueError(f"No URL configured for Fred service '{service}'")
        try:
            parsed = urlsplit(url)
            valid = (
                parsed.scheme in {"http", "https"}
                and bool(parsed.hostname)
                and "?" not in url
                and "#" not in url
                and not any(char.isspace() for char in url)
            )
            _ = parsed.port  # Validate an explicit port before constructing MCP URLs.
        except ValueError:
            valid = False
        if not valid:
            raise ValueError(f"Invalid HTTP(S) base URL for Fred service '{service}'")
        return url.rstrip("/")
