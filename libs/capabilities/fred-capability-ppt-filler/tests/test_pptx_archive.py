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

"""A small upload that declares a huge or abnormally compressed member is
refused before python-pptx inflates anything."""

from __future__ import annotations

import io
import struct
import zipfile

import pytest
from builder_decks import build_showcase_template
from fred_capability_ppt_filler.builder.analysis import analyze_template
from fred_capability_ppt_filler.builder.capability import (
    PptBuilderCapability,
    PptBuilderConfig,
)
from fred_capability_ppt_filler.capability import (
    TEMPLATE_SLOT,
    PptFillerCapability,
    PptFillerConfig,
)
from fred_capability_ppt_filler.pptx_archive import (
    UnsafeArchiveError,
    check_archive,
)
from fred_sdk.contracts.capability import (
    CapabilityIdentity,
    SaveContext,
    UploadedFile,
)
from fred_sdk.contracts.runtime import RuntimeServices
from port_fakes import FakeAssets


def _declaring_huge_member() -> bytes:
    """A real deck whose central directory claims one member inflates to ~4 GB."""
    content = bytearray(build_showcase_template())
    entry = content.find(b"PK\x01\x02")
    struct.pack_into("<I", content, entry + 24, 0xF0000000)
    return bytes(content)


def _ratio_bomb() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("ppt/slides/slide1.xml", b"\0" * (12 * 1024 * 1024))
    return buffer.getvalue()


def _uploads(content: bytes):
    return {TEMPLATE_SLOT: [UploadedFile(filename="t.pptx", content=content)]}


def _ctx() -> SaveContext:
    return SaveContext(
        identity=CapabilityIdentity(user_id="u", team_id="t", agent_instance_id="inst"),
        services=RuntimeServices(agent_assets=FakeAssets()),
    )


def test_declared_sizes_and_ratios_are_checked():
    bomb = _declaring_huge_member()
    assert len(bomb) < 1024 * 1024
    with pytest.raises(UnsafeArchiveError, match="inflates"):
        check_archive(bomb)
    with pytest.raises(UnsafeArchiveError, match="abnormally compressed"):
        check_archive(_ratio_bomb())
    check_archive(build_showcase_template())  # an ordinary deck passes


def test_the_analysis_reports_a_bomb_as_an_unreadable_template():
    result = analyze_template(_declaring_huge_member())
    assert result.inventory is None and "inflates" in result.errors[0].message


@pytest.mark.asyncio
async def test_both_capabilities_refuse_a_bomb_at_save():
    with pytest.raises(ValueError, match="inflates"):
        await PptBuilderCapability().validate_config(
            PptBuilderConfig(), _uploads(_declaring_huge_member()), _ctx()
        )
    with pytest.raises(ValueError, match="inflates"):
        await PptFillerCapability().validate_config(
            PptFillerConfig(), _uploads(_declaring_huge_member()), _ctx()
        )
