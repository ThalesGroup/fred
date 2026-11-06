# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""A capability's object namespace: confined paths, and independent lifecycles."""

import pytest
from _tracer_capability import TracerEchoCapability
from fred_core.filesystem.local_filesystem import LocalFilesystem
from fred_runtime.capabilities import CapabilityRegistry
from fred_runtime.capabilities.objects import (
    ScopedCapabilityObjects,
    bind_capability_objects,
)
from fred_runtime.conversation_filesystem import ConversationFilesystemService


@pytest.fixture
def filesystem(tmp_path) -> LocalFilesystem:
    return LocalFilesystem(root=str(tmp_path))


@pytest.mark.asyncio
async def test_writes_read_back_and_erase_inside_the_namespace(filesystem):
    objects = ScopedCapabilityObjects(filesystem, "ppt_builder")
    await objects.check()
    await objects.write("prep-1/job-1/template.pptx", b"bytes")
    assert await objects.read("prep-1/job-1/template.pptx") == b"bytes"
    assert await filesystem.exists("capabilities/ppt_builder/prep-1/job-1")
    await objects.delete("prep-1")
    await objects.delete("prep-1")  # absence is success: cleanup replays
    with pytest.raises(FileNotFoundError):
        await objects.read("prep-1/job-1/template.pptx")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "../other_capability/file",
        "prep-1/../../other_capability/file",
        "/conversations/s-1/exports/file",
        "",
        "prep-1//file",
        "prep:1/file",
    ],
)
async def test_a_path_cannot_leave_the_namespace(filesystem, path):
    objects = ScopedCapabilityObjects(filesystem, "ppt_builder")
    with pytest.raises(ValueError, match="Invalid"):
        await objects.read(path)
    with pytest.raises(ValueError, match="Invalid"):
        await objects.write(path, b"x")
    with pytest.raises(ValueError, match="Invalid"):
        await objects.delete(path)


@pytest.mark.asyncio
async def test_deleting_a_conversation_keeps_its_reusable_template(filesystem):
    objects = ScopedCapabilityObjects(filesystem, "ppt_builder")
    await objects.write("prep-1/job-1/template.pptx", b"template")
    session = "11111111-1111-4111-8111-111111111111"
    await filesystem.mkdir(f"conversations/{session}/exports")
    await filesystem.write(f"conversations/{session}/exports/deck.pptx", b"deck")
    await ConversationFilesystemService(filesystem, session).purge()
    assert not await filesystem.exists(f"conversations/{session}")
    assert await objects.read("prep-1/job-1/template.pptx") == b"template"


def test_each_capability_receives_its_own_namespace(filesystem):
    received = []

    class Bound(TracerEchoCapability):
        def bind_objects(self, objects) -> None:
            received.append(objects)

    registry = CapabilityRegistry()
    registry.register(Bound())
    bind_capability_objects(registry, filesystem)
    assert [o._root for o in received] == ["capabilities/tracer_echo"]
