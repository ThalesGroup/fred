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
Named capability errors (#1973, RFC AGENT-CAPABILITY-RFC.md §4).

Why this module exists:
- capability registration is validated at pod boot and must fail startup
  LOUDLY with an error that names exactly which rule broke and for which
  capability — a half-registered capability silently degrading an agent is
  the trust failure the RFC forbids (§3.9)
"""

from __future__ import annotations


class CapabilityError(RuntimeError):
    """Base class for all capability-system errors."""


class CapabilityRegistrationError(CapabilityError):
    """A capability could not be registered or failed boot validation."""


class DuplicateCapabilityIdError(CapabilityRegistrationError):
    """Two installed packages declare the same capability id (RFC §4)."""


class DuplicateChatPartKindError(CapabilityRegistrationError):
    """
    Two chat parts declare the same `kind` discriminator (RFC §4) — the
    `UiPart` union must stay unambiguous.
    """


class MissingRequiredEnvError(CapabilityRegistrationError):
    """A capability's `required_env` variable is absent at pod boot (RFC §7.2)."""


class DefaultOnRequiredSettingsError(CapabilityRegistrationError):
    """
    A capability combines `team_scope=default_on` with a `TeamSettingsModel`
    that has required fields (RFC §8.2) — default-on enablement cannot ask a
    team admin for mandatory settings it never collected.
    """


class UnknownCapabilityError(CapabilityError):
    """An agent references a capability this pod does not have installed (RFC §3.8)."""


class CapabilityAssemblyError(CapabilityError):
    """Selected capabilities could not be assembled into one agent."""
