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
The one check a Knowledge Base instance's configuration passes.

Used twice: when a team writes the configuration, and again before a pod is
handed it. Twice with the same code, because the two questions differ only in
when they are asked — a definition republished with different declared fields
leaves stored values that were valid when written and are not any more, and a
handler promised validated configuration must not be the one to discover it.

The checking itself is `common.field_values`, shared with the two other write
paths that validate declared fields. What is Knowledge-Base-specific is here:
the exception, and the strictest of the available options.
"""

from __future__ import annotations

from typing import Any, Mapping

from fred_sdk.contracts.models import FieldSpec, TuningValue

from control_plane_backend.common.field_values import validate_field_values


class InstanceConfigurationInvalid(Exception):
    """A submitted or stored configuration does not satisfy its declaration.

    Carries the offending field so a caller can point at it rather than at the
    form as a whole.
    """

    http_status = 422

    def __init__(self, message: str, *, field_key: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.field_key = field_key


def _fail(key: str, detail: str) -> InstanceConfigurationInvalid:
    return InstanceConfigurationInvalid(f"{key}: {detail}", field_key=key)


def _fail_unknown(keys: list[str]) -> InstanceConfigurationInvalid:
    unknown = sorted(keys)
    return InstanceConfigurationInvalid(
        f"Unknown configuration field(s): {unknown!r}", field_key=unknown[0]
    )


def validate_instance_configuration(
    declared: list[FieldSpec], submitted: Mapping[str, Any]
) -> dict[str, TuningValue]:
    """Return the declared values, unchanged, or say which field is wrong.

    Unknown keys are refused rather than dropped: a team that misspells a key
    would otherwise watch its value vanish and the handler run without it.

    A declared default fills a field the submission omits, so what the handler
    receives is complete — but nothing is coerced, converted or reformatted.
    """
    return validate_field_values(
        declared,
        submitted,
        fail=_fail,
        fail_unknown=_fail_unknown,
        fill_defaults=True,
    )
