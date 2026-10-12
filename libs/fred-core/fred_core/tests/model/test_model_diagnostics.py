# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
from types import SimpleNamespace

import httpx
import pytest
from fred_core.common import ModelConfiguration
from fred_core.model.diagnostics import (
    ModelHttpObservation,
    active_model_http,
    effective_model_settings,
    log_model_settings,
    observe_model_response,
)
from fred_core.model.factory import _info_provider
from fred_core.model.http_clients import get_shared_stack, shutdown_shared_clients


@pytest.mark.parametrize("allow_ids", [False, True])
def test_headers_are_allowlisted_and_body_not_read(allow_ids):
    response = httpx.Response(
        200,
        headers={
            "x-request-id": "synthetic-id",
            "apim-request-id": "https://private/?secret=value",
            "set-cookie": "private-cookie",
            "authorization": "private-header",
        },
        stream=httpx.ByteStream(b"private-body"),
    )
    observation = ModelHttpObservation(allow_request_ids=allow_ids)
    token = active_model_http.set(observation)
    try:
        observe_model_response(response)
    finally:
        active_model_http.reset(token)
    assert not response.is_stream_consumed
    assert observation.fields["http_status"] == 200
    assert ("x_request_id" in observation.fields) == allow_ids
    assert "private" not in repr(observation.fields)
    response.close()


def test_safe_configuration_does_not_dump_model_or_settings(caplog):
    import logging

    caplog.set_level(logging.INFO)
    model = SimpleNamespace(
        streaming=True,
        stream_chunk_timeout=45,
        max_retries=0,
        request_timeout=httpx.Timeout(9, read=51),
        api_key="private-key",  # pragma: allowlist secret
        model_kwargs={"secret": "private-option"},  # nosec B105 # pragma: allowlist secret
    )
    settings = effective_model_settings(model)
    assert settings["timeout_read_s"] == 51
    assert settings["timeout_connect_s"] == 9
    assert settings["stream_chunk_timeout"] == 45
    log_model_settings.cache_clear()
    log_model_settings("openai", "synthetic-model", tuple(settings.items()))
    log_model_settings("openai", "synthetic-model", tuple(settings.items()))
    _info_provider(
        ModelConfiguration(provider="openai", name="synthetic-model"),
        {
            "base_url": "https://private/",
            "default_headers": {"custom": "private-header"},
        },
    )
    assert "private" not in caplog.text
    assert (
        sum("event=llm_model_configuration" in r.getMessage() for r in caplog.records)
        == 1
    )


def test_shared_transport_keeps_effective_limits_and_hooks(caplog, monkeypatch):
    import logging

    caplog.set_level(logging.DEBUG)
    from fred_core.model import http_clients

    for name in ("_SHARED_TUNING", "_SYNC_CLIENT", "_ASYNC_CLIENT"):
        monkeypatch.setattr(http_clients, name, None)
    try:
        cfg = ModelConfiguration(provider="openai", name="synthetic-model")
        tuning, sync, async_client = get_shared_stack(
            cfg,
            settings={
                "timeout": {"read": 71},
                "default_headers": {"custom": "private-header"},
            },
        )
        second, sync2, async2 = get_shared_stack(
            cfg, settings={"timeout": {"read": 99}}
        )
        assert second.timeout.read == tuning.timeout.read == 71
        assert sync2 is sync and async2 is async_client
        assert (
            len(sync.event_hooks["response"])
            == len(async_client.event_hooks["response"])
            == 1
        )
        assert "ignoring new tuning" in caplog.text
        assert "private-header" not in caplog.text
    finally:
        shutdown_shared_clients()


def test_constructed_client_timeout_and_tuple_are_reported():
    tuple_settings = effective_model_settings(SimpleNamespace(request_timeout=(5, 71)))
    assert tuple_settings["timeout_connect_s"] == 5
    assert tuple_settings["timeout_read_s"] == 71
    sdk_settings = effective_model_settings(
        SimpleNamespace(
            request_timeout=9,
            root_async_client=SimpleNamespace(timeout=httpx.Timeout(13)),
        )
    )
    assert sdk_settings["timeout_read_s"] == 13
