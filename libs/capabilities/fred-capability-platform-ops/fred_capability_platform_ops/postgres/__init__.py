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

"""`platform_postgres` — read-only SQL over the platform database."""

from fred_capability_platform_ops.postgres.capability import (
    PLATFORM_POSTGRES_TOOL_REF,
    PlatformPostgresCapability,
    PlatformPostgresConfig,
)

__all__ = [
    "PLATFORM_POSTGRES_TOOL_REF",
    "PlatformPostgresCapability",
    "PlatformPostgresConfig",
]
