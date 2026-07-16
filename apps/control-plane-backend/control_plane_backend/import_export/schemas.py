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

"""Typed bundle schemas for declarative platform provisioning.

AUTHZ-07 Part 8 §40.2 / `docs/swift/rfc/PLATFORM-IMPORT-RFC.md` §6. `BundleUserEntry`
is the typed shape of each `users.json` bundle entry — it carries both the
identity-creation fields consumed by `importer.py::_provision_bundle_identities`
(email/first_name/last_name/password, all optional) and the authorization
fields consumed by the pre-existing role-provisioning phase
(teams/team_roles/platform_roles). One format, because it's one file: each
phase reads what it needs from the same entry and ignores the rest.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class BundleUserEntry(BaseModel):
    """One `users.json` bundle entry.

    Why this type exists:
    - `KBundle.demo_users()` used to return raw `dict[str, Any]` rows; typing
      this shape catches malformed bundles at parse time instead of failing
      deep inside a provisioning phase with a confusing `KeyError`/`AttributeError`

    How to use it:
    - `BundleUserEntry.model_validate(raw_entry)` per row, mirroring the
      try/except-`KeyError` pattern `KBundle.openfga_tuples()` already uses
      around the zip read itself

    Example:
    - `BundleUserEntry(username="alice", platform_roles=["admin"])`
    """

    username: str
    # Identity phase (`_provision_bundle_identities`) — optional; an entry with
    # no `password` is assumed to already exist in Keycloak and is never
    # force-created.
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    password: str | None = None
    # Role phase (`_resolve_bundle_usernames` / `_apply_bundle_user_roles`) —
    # unchanged from the shape documented in `PLATFORM-IMPORT-RFC.md` §6.
    teams: list[str] = Field(default_factory=list)
    team_roles: dict[str, list[str]] = Field(default_factory=dict)
    platform_roles: list[str] = Field(default_factory=list)
