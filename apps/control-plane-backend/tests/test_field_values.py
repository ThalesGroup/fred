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

"""The shared field validator, and the options its three callers disagree on.

One test per option: each encodes a difference between the Knowledge Base,
team-settings and managed-tuning write paths that had to survive them being
converged onto a single validator.
"""

from typing import Any

import pytest
from control_plane_backend.common.field_values import validate_field_values
from control_plane_backend.config.models import ManagedAgentFieldSpec
from control_plane_backend.product.service import (
    EnrollmentError,
    _validate_tuning_field_values,
)
from fred_sdk.contracts.models import FieldSpec


class _Invalid(Exception):
    pass


def _fail(key: str, detail: str) -> Exception:
    return _Invalid(f"{key}: {detail}")


def _validate(declared: list[Any], submitted: dict[str, Any], **options: Any):
    return validate_field_values(declared, submitted, fail=_fail, **options)


def test_both_field_spec_models_are_accepted_without_conversion() -> None:
    """Duck-typed: the two structurally identical models validate the same.

    Every member the protocol declares is read here, on both models, so a
    missing one shows up as a failure rather than as a skipped check.
    """
    sdk = FieldSpec(
        key="hosts",
        title="Hosts",
        type="array",
        item_type="string",
        pattern=r"[a-z.]+",
        required=True,
        default=["a.test"],
        min=1,
        max=10,
    )
    managed = ManagedAgentFieldSpec(
        key="hosts",
        title="Hosts",
        type="array",
        item_type="string",
        pattern=r"[a-z.]+",
        required=True,
        default=["a.test"],
        min=1,
        max=10,
    )
    for spec in (sdk, managed):
        assert _validate([spec], {"hosts": ["a.test"]}) == {"hosts": ["a.test"]}
        assert _validate([spec], {}, fill_defaults=True) == {"hosts": ["a.test"]}
        with pytest.raises(_Invalid):
            _validate([spec], {"hosts": ["NOPE"]})
        with pytest.raises(_Invalid):
            _validate([spec], {})
        with pytest.raises(_Invalid):
            _validate([spec], {"hosts": "a.test"})


def test_unknown_keys_are_dropped_when_no_refusal_is_supplied() -> None:
    """Managed tuning tolerates them; the two other paths refuse the write."""
    declared = [FieldSpec(key="a", type="string", title="A")]

    assert _validate(declared, {"a": "x", "zz": 1}) == {"a": "x"}
    with pytest.raises(_Invalid):
        _validate(
            declared,
            {"a": "x", "zz": 1},
            fail_unknown=lambda keys: _Invalid(f"unknown: {sorted(keys)!r}"),
        )


def test_required_is_only_enforced_when_the_caller_asks_for_it() -> None:
    """A tuning write may carry a subset of the fields; a form may not."""
    declared = [FieldSpec(key="a", type="string", title="A", required=True)]

    assert _validate(declared, {}, enforce_required=False) == {}
    with pytest.raises(_Invalid):
        _validate(declared, {})


def test_a_declared_default_fills_an_omitted_field_and_is_itself_checked() -> None:
    with pytest.raises(_Invalid):
        _validate(
            [FieldSpec(key="a", type="integer", title="A", default="five")],
            {},
            fill_defaults=True,
        )

    declared = [FieldSpec(key="a", type="integer", title="A", default=5)]
    assert _validate(declared, {}, fill_defaults=True) == {"a": 5}
    assert _validate(declared, {}) == {}


def test_enum_applies_to_select_alone_unless_every_type_is_asked_for() -> None:
    declared = [FieldSpec(key="a", type="string", title="A", enum=["x"])]

    assert _validate(declared, {"a": "y"}) == {"a": "y"}
    with pytest.raises(_Invalid):
        _validate(declared, {"a": "y"}, enum_on_every_type=True)


def test_strict_array_items_answer_to_the_field_they_belong_to() -> None:
    """Strict: a declared item type, and the field's own constraints on each
    item. Lenient: any scalar, and an undeclared item type is not an error."""
    untyped = [FieldSpec(key="a", type="array", title="A")]
    assert _validate(untyped, {"a": [1, "x"]}, strict_array_items=False) == {
        "a": [1, "x"]
    }
    with pytest.raises(_Invalid):
        _validate(untyped, {"a": [1]})

    bounded = [FieldSpec(key="a", type="array", title="A", item_type="integer", max=10)]
    assert _validate(bounded, {"a": [99]}, strict_array_items=False) == {"a": [99]}
    with pytest.raises(_Invalid):
        _validate(bounded, {"a": [99]})


def test_the_tuning_write_path_keeps_the_tolerances_it_had() -> None:
    """A wrong option at this call site is what would break managed agents:
    a partial write, an unknown key, a loose array and enum on every type."""
    declared = [
        ManagedAgentFieldSpec(key="a", type="string", title="A", required=True),
        ManagedAgentFieldSpec(key="b", type="array", title="B"),
        ManagedAgentFieldSpec(key="c", type="string", title="C", enum=["x"]),
    ]

    assert _validate_tuning_field_values(
        field_specs=declared,
        submitted_values={"b": [1, "x"], "zz": "dropped"},
        context_label="test",
    ) == {"b": [1, "x"]}

    with pytest.raises(EnrollmentError) as raised:
        _validate_tuning_field_values(
            field_specs=declared,
            submitted_values={"c": "y"},
            context_label="test",
        )
    assert raised.value.http_status == 422


def test_a_text_check_refuses_a_value_in_the_caller_s_own_words() -> None:
    declared = [FieldSpec(key="a", type="prompt", title="A")]

    with pytest.raises(_Invalid, match="a: no angle brackets"):
        _validate(
            declared,
            {"a": "<tools>"},
            text_check=lambda v: "no angle brackets" if "<" in v else None,
        )
