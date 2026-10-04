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

"""Scope classification of capability settings: reset, asset keys, guard."""

from __future__ import annotations

from typing import Annotated, Optional

from fred_sdk.contracts.capability import (
    AssetKey,
    Public,
    ScopePrivate,
    asset_keys,
    reset_scope_private,
    unclassified_reference_fields,
    unclassified_reference_specs,
)
from fred_sdk.contracts.models import FieldSpec
from pydantic import BaseModel, ConfigDict, Field


class _Key(BaseModel):
    key: Public[str]
    folder: Public[Optional[str]] = None
    folder_tag_id: ScopePrivate[Optional[str]] = None


class _Slide(BaseModel):
    slide: int
    keys: list[_Key] = Field(default_factory=list)


class _Config(BaseModel):
    library_tag_ids: ScopePrivate[list[str]] = []
    top_k: int = 8
    template_key: Annotated[str, AssetKey("template")] = "template.pptx"
    slides: list[_Slide] = Field(default_factory=list)


def _config() -> _Config:
    return _Config(
        library_tag_ids=["lib-a", "lib-b"],
        top_k=3,
        slides=[
            _Slide(
                slide=1,
                keys=[_Key(key="logo", folder="Logos", folder_tag_id="tag-a")],
            )
        ],
    )


def test_reset_clears_flat_and_nested_scope_private_fields_only() -> None:
    reset = reset_scope_private(_config())

    assert reset.library_tag_ids == []
    assert reset.slides[0].keys[0].folder_tag_id is None
    assert reset.slides[0].keys[0].folder == "Logos"
    assert reset.slides[0].keys[0].key == "logo"
    assert reset.top_k == 3
    assert reset.template_key == "template.pptx"


def test_reset_leaves_the_source_untouched() -> None:
    source = _config()
    reset_scope_private(source)

    assert source.library_tag_ids == ["lib-a", "lib-b"]
    assert source.slides[0].keys[0].folder_tag_id == "tag-a"


def test_reset_applies_catalog_declared_fields_of_an_open_model() -> None:
    class _Open(BaseModel):
        model_config = ConfigDict(extra="allow")

    stored = _Open.model_validate(
        {"chat_options.bound_library_ids": ["lib-a"], "chat_options.attach_files": True}
    )
    specs = [
        FieldSpec(
            key="chat_options.bound_library_ids",
            type="array",
            item_type="string",
            title="t",
            default=[],
            scope_private=True,
        ),
        FieldSpec(key="chat_options.attach_files", type="boolean", title="t"),
    ]

    dumped = reset_scope_private(stored, field_specs=specs).model_dump()

    assert dumped == {
        "chat_options.bound_library_ids": [],
        "chat_options.attach_files": True,
    }


def test_asset_keys_groups_configuration_files_by_slot() -> None:
    assert asset_keys(_config()) == {"template": ["template.pptx"]}
    assert asset_keys(_config().model_copy(update={"template_key": ""})) == {}


def test_guard_accepts_a_fully_classified_model() -> None:
    assert unclassified_reference_fields(_Config) == []


def test_guard_names_unclassified_reference_fields_at_any_depth() -> None:
    class _Inner(BaseModel):
        folder_tag_id: Optional[str] = None
        enabled: bool = False

    class _Outer(BaseModel):
        document_uids: list[str] = []
        bind_libraries: bool = False
        mode: str = "read"
        inner: list[_Inner] = []

    assert unclassified_reference_fields(_Outer) == [
        "document_uids",
        "inner.folder_tag_id",
    ]


def test_guard_checks_catalog_declared_text_fields() -> None:
    specs = [
        FieldSpec(
            key="chat_options.bound_library_ids",
            type="array",
            item_type="string",
            title="t",
        ),
        FieldSpec(key="chat_options.libraries_binding", type="boolean", title="t"),
        FieldSpec(
            key="server.base_path", type="string", title="t", scope_private=False
        ),
    ]

    assert unclassified_reference_specs(specs) == ["chat_options.bound_library_ids"]
