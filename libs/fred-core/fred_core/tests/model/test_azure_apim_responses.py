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

import asyncio
from types import SimpleNamespace

import httpx
import pytest
from fred_core.common import ModelConfiguration
from fred_core.model import factory
from langchain_openai import AzureChatOpenAI


@pytest.mark.parametrize("use_responses_api", [False, True])
def test_azure_apim_selects_endpoint_for_chat_api(
    monkeypatch: pytest.MonkeyPatch, use_responses_api: bool
) -> None:
    monkeypatch.setenv("AZURE_APIM_SUBSCRIPTION_KEY", "test-subscription")
    monkeypatch.setenv("AZURE_AD_CLIENT_SECRET", "test-secret")
    sync_client = httpx.Client()
    async_client = httpx.AsyncClient()
    monkeypatch.setattr(
        factory,
        "get_shared_stack",
        lambda *_args, **_kwargs: (
            SimpleNamespace(timeout=httpx.Timeout(30)),
            sync_client,
            async_client,
        ),
    )
    settings = {
        "azure_tenant_id": "00000000-0000-0000-0000-000000000001",
        "azure_ad_client_id": "00000000-0000-0000-0000-000000000002",
        "azure_ad_client_scope": "api://test/.default",
        "azure_apim_base_url": "https://apim.example.test",
        "azure_apim_resource_path": "/ai-models/openai",
        "azure_openai_api_version": "2024-06-01",
        "use_responses_api": use_responses_api,
        "stream_usage": False,
        "temperature": None,
    }

    try:
        model = factory.get_model(
            ModelConfiguration(
                provider="azure-apim", name="gpt-6-astra", settings=settings
            )
        )
        assert isinstance(model, AzureChatOpenAI)
        if use_responses_api:
            assert model.root_client.base_url.path == "/ai-models/openai/v1/"
            assert model.model_name == "gpt-6-astra"
        else:
            assert "/deployments/gpt-6-astra/chat/completions" in str(
                model.root_client.base_url
            )
        assert model.use_responses_api is use_responses_api
    finally:
        sync_client.close()
        asyncio.run(async_client.aclose())
