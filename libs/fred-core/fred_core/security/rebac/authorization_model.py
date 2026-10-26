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

"""Validate the exact Weaver model without initializing an authorization engine."""

import asyncio
import json
import os
from importlib.resources import files
from urllib.parse import quote

import httpx
from fred_core.security.rebac.authorization_binding import (
    AuthorizationBinding,
    AuthorizationBindingError,
)
from fred_core.security.structure import OpenFgaRebacConfig


class AuthorizationModelError(AuthorizationBindingError):
    """Model validation failed; messages contain no credentials or response bodies."""


class CanonicalModelError(AuthorizationModelError):
    """The installed canonical model resource is missing or invalid."""


class AuthorizationModelNotFoundError(AuthorizationModelError):
    """The published store or exact model does not exist remotely."""


class InvalidAuthorizationModelResponseError(AuthorizationModelError):
    """OpenFGA returned malformed JSON or an invalid model envelope."""


class IncompatibleAuthorizationModelError(AuthorizationModelError):
    """The published model differs from the canonical Weaver contract."""


class AuthorizationModelCommunicationError(AuthorizationModelError):
    """OpenFGA access failed, including authentication, HTTP and transport errors."""


def _reject_non_json_constant(value: str) -> None:
    # Python accepts NaN/Infinity by default; serde_json does not.
    raise ValueError("Non-JSON constant")


def _model_shape_valid(model: object) -> bool:
    return (
        isinstance(model, dict)
        and isinstance(model.get("schema_version"), str)
        and bool(model["schema_version"])
        and isinstance(model.get("type_definitions"), list)
        and bool(model["type_definitions"])
        and all(
            isinstance(definition, dict)
            and isinstance(definition.get("type"), str)
            and bool(definition["type"])
            for definition in model["type_definitions"]
        )
    )


def _empty_conditions(model: dict[str, object]) -> bool:
    conditions = model.get("conditions")
    return conditions is None or (isinstance(conditions, dict) and not conditions)


def _read_canonical_model() -> dict[str, object]:
    try:
        raw = (
            files("fred_core.security.rebac").joinpath("weaver-model.json").read_bytes()
        )
    except OSError:
        raise CanonicalModelError(
            "Canonical Weaver model resource is unavailable"
        ) from None
    try:
        model = json.loads(raw, parse_constant=_reject_non_json_constant)
    except (ValueError, RecursionError):
        raise CanonicalModelError(
            "Canonical Weaver model resource is invalid JSON"
        ) from None
    if not _model_shape_valid(model) or not _empty_conditions(model):
        raise CanonicalModelError(
            "Canonical Weaver model resource has an invalid shape"
        )
    try:
        model["type_definitions"] = _normalized_model(model["type_definitions"])
    except RecursionError:
        raise CanonicalModelError(
            "Canonical Weaver model resource is too deeply nested"
        ) from None
    return model


def _normalized_model(value: object) -> object:
    # Exact recursive defaults from control-plane/src/fga.rs::normalized_model.
    # Retain unknown keys and array order, including nonempty authorization terms.
    if isinstance(value, dict):
        return {
            key: _normalized_model(item)
            for key, item in value.items()
            if not (
                (key in ("object", "condition", "module") and item == "")
                or (key in ("metadata", "source_info") and item is None)
                or (key == "relations" and isinstance(item, dict) and not item)
            )
        }
    if isinstance(value, list):
        return [_normalized_model(item) for item in value]
    return value


async def validate_authorization_binding(
    binding: AuthorizationBinding,
    config: OpenFgaRebacConfig,
    *,
    token: str | None = None,
) -> AuthorizationBinding:
    """GET and validate the published model, returning the same immutable binding.

    Call after read_authorization_binding has released its SQL connection. This
    function owns and closes its HTTP client, including on failure/cancellation.
    Only endpoint, token, headers, timeout and configured store come from config;
    store/model selection comes exclusively from binding. No retry or mutation.
    Raises AuthorizationBindingError for a configured-store mismatch, ValueError
    for missing credentials, and AuthorizationModelError subclasses otherwise.
    """
    if binding.configured_store != config.store_name:
        raise AuthorizationBindingError(
            "Configured OpenFGA store differs from published authorization store"
        )
    expected = await asyncio.to_thread(_read_canonical_model)
    resolved_token = token or os.getenv(config.token_env_var)
    if not resolved_token:
        raise ValueError("OpenFGA token must be provided via parameter or environment")
    timeout = (
        None if config.timeout_millisec is None else config.timeout_millisec / 1000
    )
    store = quote(binding.active_store, safe="").replace(".", "%2E")
    model = quote(binding.model_id, safe="").replace(".", "%2E")
    try:
        headers = httpx.Headers(config.headers)
        headers["Authorization"] = f"Bearer {resolved_token}"
        headers["Accept"] = "application/json"
        async with asyncio.timeout(timeout):
            async with httpx.AsyncClient(
                base_url=str(config.api_url).rstrip("/") + "/",
                headers=headers,
                timeout=timeout,
                follow_redirects=False,
            ) as client:
                response = await client.get(
                    f"stores/{store}/authorization-models/{model}"
                )
    except (httpx.HTTPError, httpx.InvalidURL, TimeoutError, ValueError):
        raise AuthorizationModelCommunicationError(
            "Cannot retrieve published OpenFGA model"
        ) from None

    if response.status_code == 404:
        raise AuthorizationModelNotFoundError(
            "Published OpenFGA store or model was not found"
        )
    if response.status_code != 200:
        raise AuthorizationModelCommunicationError(
            f"OpenFGA model retrieval failed (HTTP {response.status_code})"
        )
    try:
        # SDK models discard unknown fields. Raw JSON preserves comparison input.
        reply = json.loads(response.content, parse_constant=_reject_non_json_constant)
    except (ValueError, RecursionError):
        raise InvalidAuthorizationModelResponseError(
            "OpenFGA model response is not valid JSON"
        ) from None
    actual = reply.get("authorization_model") if isinstance(reply, dict) else None
    if (
        not isinstance(actual, dict)
        or not _model_shape_valid(actual)
        or not isinstance(actual.get("id"), str)
        or not actual["id"]
    ):
        raise InvalidAuthorizationModelResponseError(
            "OpenFGA model response has an invalid shape"
        )
    try:
        compatible = (
            actual["id"] == binding.model_id
            and actual["schema_version"] == expected["schema_version"]
            and _normalized_model(actual["type_definitions"])
            == expected["type_definitions"]
            and _empty_conditions(actual)
        )
    except RecursionError:
        raise InvalidAuthorizationModelResponseError(
            "OpenFGA model response is too deeply nested"
        ) from None
    if not compatible:
        raise IncompatibleAuthorizationModelError(
            "Published OpenFGA model is incompatible"
        )
    return binding
