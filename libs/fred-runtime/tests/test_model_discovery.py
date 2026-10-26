# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Prepared M4 cutover cases: pod boot and selection perform no discovery."""

from types import SimpleNamespace
from typing import cast

import httpx
import pytest
from fred_runtime.app.agent_app import _build_chat_model_factory
from fred_runtime.app.config import AgentPodConfig
from fred_runtime.model_routing.provider import RoutedChatModelFactory
from fred_runtime.runtime_support.authority import AuthorityLostError
from fred_sdk.contracts.context import BoundRuntimeContext
from fred_sdk.contracts.models import AgentDefinition


def test_pod_model_factory_does_not_fetch_discovery(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("The pod must never perform model discovery")

    monkeypatch.setattr(httpx.Client, "get", forbidden)
    monkeypatch.setattr(httpx.AsyncClient, "get", forbidden)
    factory = _build_chat_model_factory(
        cast(AgentPodConfig, SimpleNamespace(inference_credentials=()))
    )
    assert isinstance(factory, RoutedChatModelFactory)


def test_catalog_or_configuration_cannot_authorize_a_turn():
    factory = RoutedChatModelFactory()
    with pytest.raises(AuthorityLostError):
        factory.build(
            cast(AgentDefinition, SimpleNamespace(agent_id="template")),
            cast(BoundRuntimeContext, SimpleNamespace()),
        )
