"""Only current, bound capability result paths are readable during a turn."""

from typing import cast

import pytest
from fred_core.filesystem.structures import BaseFilesystem
from fred_runtime.capabilities.preparation_artifacts import BoundPreparationArtifacts


class Filesystem:
    async def read(self, path: str) -> bytes:
        return path.encode()


@pytest.mark.asyncio
async def test_artifact_reader_is_bound_to_published_result() -> None:
    reader = BoundPreparationArtifacts(
        cast(BaseFilesystem, Filesystem()),
        {"ppt_builder": "capability-results/job-1/1/result.json"},
        {"ppt_builder:platform:template": {"overrides": []}},
    )
    assert reader.has_result("ppt_builder")
    assert not reader.has_result("ppt_builder:platform:template")
    assert reader.settings("ppt_builder:platform:template") == {"overrides": []}
    assert await reader.read_result("other") is None
    assert await reader.read_result("ppt_builder") == (
        b"capability-results/job-1/1/result.json"
    )
    assert await reader.read_sibling("ppt_builder", "template.pptx") == (
        b"capability-results/job-1/1/template.pptx"
    )
    with pytest.raises(ValueError):
        await reader.read_sibling("ppt_builder", "../secret")
