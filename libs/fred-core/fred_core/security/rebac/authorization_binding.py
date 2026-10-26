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

"""Read the authorization binding published by the Weaver Control Plane."""

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.exc import MultipleResultsFound
from sqlalchemy.ext.asyncio import AsyncEngine


@dataclass(frozen=True)
class AuthorizationBinding:
    """Published identifiers; the referenced OpenFGA model is not validated here."""

    configured_store: str
    active_store: str
    model_id: str


class AuthorizationBindingError(RuntimeError):
    """Missing, inconsistent or unreadable publication, with credential-safe detail."""


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AuthorizationBindingError(
            f"Authorization binding requires nonblank text for {field}"
        )
    return value


async def read_authorization_binding(
    engine: AsyncEngine,
    *,
    expected_configured_store: str,
) -> AuthorizationBinding:
    """Read one publication using a borrowed engine, without OpenFGA calls.

    expected_configured_store is the configuration's store_name, compared exactly.
    Raises AuthorizationBindingError for invalid input, publication or SQL access.
    The connection is released after reading; the caller retains engine ownership.
    """
    expected = _required_text(expected_configured_store, "expected configured store")
    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                text(
                    "select configured_store, active_store, model_id "
                    "from authorization_store where singleton"
                )
            )
            row = result.mappings().one_or_none()
    except MultipleResultsFound:
        raise AuthorizationBindingError(
            "Authorization binding is invalid: multiple singleton rows"
        ) from None
    except Exception:
        # Drivers may raise outside SQLAlchemy's exception hierarchy. Do not expose
        # connection details through their messages or chained tracebacks.
        raise AuthorizationBindingError(
            "Cannot read authorization_store; check database access and the "
            "Control Plane schema"
        ) from None

    if row is None:
        raise AuthorizationBindingError(
            "Authorization binding is missing; initialize Control Plane "
            "authorization with serve first"
        )
    binding = AuthorizationBinding(
        configured_store=_required_text(row["configured_store"], "configured_store"),
        active_store=_required_text(row["active_store"], "active_store"),
        model_id=_required_text(row["model_id"], "model_id"),
    )
    if binding.configured_store != expected:
        raise AuthorizationBindingError(
            "Configured OpenFGA store differs from published authorization store"
        )
    return binding
