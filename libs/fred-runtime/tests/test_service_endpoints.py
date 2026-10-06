# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Service resolution uses only the existing outbound pod addresses."""

import pytest
from fred_runtime.app.config import AgentPodConfig
from fred_runtime.app.service_endpoints import ConfiguredServiceEndpoints
from fred_sdk.contracts.services import FredService, ServiceEndpointsPort


def test_configured_service_urls(minimal_config: AgentPodConfig) -> None:
    minimal_config.ai.knowledge_flow_url = "http://[::1]:9111/custom/kf/"
    minimal_config.platform.control_plane_url = "https://cp.example:9443/custom/cp"
    services: ServiceEndpointsPort = ConfiguredServiceEndpoints(minimal_config)

    assert (
        services.get_base_url(FredService.KNOWLEDGE_FLOW)
        == "http://[::1]:9111/custom/kf"
    )
    assert (
        services.get_base_url(FredService.CONTROL_PLANE)
        == "https://cp.example:9443/custom/cp"
    )


def test_missing_service_fails_when_requested(minimal_config: AgentPodConfig) -> None:
    services = ConfiguredServiceEndpoints(minimal_config)
    assert services.get_base_url(FredService.KNOWLEDGE_FLOW)
    with pytest.raises(ValueError, match="No URL configured.*control_plane"):
        services.get_base_url(FredService.CONTROL_PLANE)


@pytest.mark.parametrize(
    "url",
    [
        "",
        "kf.example:8111/api",
        "ftp://kf/api",
        "http:///api",
        "https://kf:invalid/api",
        "https://kf:99999/api",
        "https://kf/api?query=1",
        "https://kf/api#fragment",
        "https://kf/api?",
        "https://kf/api#",
        "https://kf/ api",
    ],
)
def test_invalid_service_address_fails(
    minimal_config: AgentPodConfig, url: str
) -> None:
    minimal_config.ai.knowledge_flow_url = url
    with pytest.raises(ValueError, match="Fred service 'knowledge_flow'"):
        ConfiguredServiceEndpoints(minimal_config).get_base_url(
            FredService.KNOWLEDGE_FLOW
        )
