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

"""
Per-capability OpenAPI dumper (#1979, RFC §9.1).

Why this module exists:
- each capability's frontend folder generates a typed RTK Query slice from the
  capability router's OWN OpenAPI document — only that capability's routes and
  schemas, no neighbours — so its hooks stay isolated to the capability plugin
- the document is produced from a throwaway `FastAPI()` wrap of the router, at
  the SAME path shape the frontend's dynamic base query resolves
  (`capabilityBaseUrl(id)` == `{pod}/capabilities/{id}`), so paths in the dump
  are relative to that base and are NOT re-prefixed

How to use:
- `python -m fred_runtime dump-openapi <capability_id>` prints the JSON
- the capability's `<id>OpenApiConfig.json` codegen config points its
  `schemaFile` at the written document
"""

from __future__ import annotations

from typing import Any

from fred_sdk.contracts.capability import AgentCapability


def dump_capability_openapi(
    capability: AgentCapability[Any, Any, Any],
) -> dict[str, Any]:
    """
    Return the OpenAPI document for one capability's router, or raise
    ``ValueError`` when the capability ships no ``router``.

    The router is wrapped in an isolated ``FastAPI()`` with NO extra prefix:
    the frontend base query already targets `{pod}/capabilities/{id}`, so the
    document's paths must be relative to that base.
    """

    from fastapi import FastAPI

    router = capability.manifest.router
    if router is None:
        raise ValueError(
            f"Capability '{capability.manifest.id}' declares no router; "
            "nothing to dump."
        )
    app = FastAPI(
        title=f"capability:{capability.manifest.id}",
        version=capability.manifest.version,
    )
    app.include_router(router)
    return app.openapi()
