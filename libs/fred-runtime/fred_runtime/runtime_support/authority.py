# Copyright Thales 2025
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

"""Typed reasons a run stops for. Raised by outbound call sites, turned into the
terminal error event by the engines."""

from __future__ import annotations

from fred_sdk.contracts.runtime import RunStopError

__all__ = [
    "AuthorityLostError",
    "DelegationUnavailableError",
    "RunStopError",
]


class AuthorityLostError(RunStopError):
    """A receiver refused the run's authority (401/403 on a delegated call)."""

    reason = "authority_lost"


class DelegationUnavailableError(RunStopError):
    """act_for_people is on but cannot be used (missing configuration, refused server)."""

    reason = "delegation_unavailable"
