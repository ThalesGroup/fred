# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Object operations use real PostgreSQL locks/FKs with deployment role limits."""

import asyncio

import pytest
from fred_runtime.conversation_filesystem import (
    _FILESYSTEM_WRITES,
    ConversationFilesystemService,
)
from fred_runtime.runtime_support.session_fence import (
    SessionFence,
    SessionPurgedError,
    SessionWritesPending,
)
from fred_sdk.contracts.runtime import ConversationScratchpadStorageError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from test_conversation_filesystem import _MemoryFilesystem
from test_session_ownership import OTHER, SESSION, _migrate
from test_session_ownership import database as database

pytestmark = [
    pytest.mark.integration,
    pytest.mark.integration_postgres,
    pytest.mark.asyncio,
]


async def _delete_root(cp):
    async with cp.begin() as conn:
        await conn.execute(
            text("DELETE FROM session_metadata WHERE session_id=:id"), {"id": SESSION}
        )


async def test_root_restricted_until_objects_are_erased_and_cannot_reopen(database):
    cp, runtime = database
    await _migrate(runtime)
    fence = SessionFence(runtime)
    token = await fence.begin_filesystem_write(SESSION)
    with pytest.raises(IntegrityError):
        await _delete_root(cp)
    await fence.end_filesystem_write(token)
    # No writer remains, but its content manifest still owns external files.
    with pytest.raises(IntegrityError):
        await _delete_root(cp)
    await fence.close(SESSION)
    await fence.acknowledge_purge(SESSION)
    with pytest.raises(SessionPurgedError):
        await SessionFence(runtime).begin_filesystem_write(SESSION)
    await _delete_root(cp)
    for _ in range(2):
        await SessionFence(runtime).close(SESSION)
        await SessionFence(runtime).acknowledge_purge(SESSION)
        with pytest.raises(IntegrityError):
            await SessionFence(runtime).begin_filesystem_write(SESSION)
    # A missing root for one conversation does not close its neighbour.
    other_token = await SessionFence(runtime).begin_filesystem_write(OTHER)
    await fence.end_filesystem_write(other_token)


async def test_cancelled_file_writer_blocks_purge_until_actual_completion(database):
    cp, runtime = database
    await _migrate(runtime)
    entered, release = asyncio.Event(), asyncio.Event()

    class SlowFilesystem(_MemoryFilesystem):
        async def write(self, path, data):
            entered.set()
            await release.wait()
            await super().write(path, data)

    fence = SessionFence(runtime)
    storage = SlowFilesystem()
    service = ConversationFilesystemService(storage, SESSION, fence=fence)
    writer = asyncio.create_task(service.scratchpad().write_text("note", "private"))
    await entered.wait()
    writer.cancel()
    with pytest.raises(asyncio.CancelledError):
        await writer
    # Another replica sees the committed intent after caller cancellation.
    with pytest.raises(SessionWritesPending):
        await SessionFence(runtime).close(SESSION)
    with pytest.raises(IntegrityError):
        await _delete_root(cp)
    release.set()
    await asyncio.gather(*tuple(_FILESYSTEM_WRITES))
    await fence.close(SESSION)
    await service.purge()
    await fence.acknowledge_purge(SESSION)
    await _delete_root(cp)
    assert storage.files == {}
    with pytest.raises(ConversationScratchpadStorageError):
        await service.namespace("deep", max_bytes=1024, max_files=10).write_bytes(
            "late.pptx", b"private"
        )
    await (
        ConversationFilesystemService(storage, OTHER, fence=fence)
        .namespace("deep", max_bytes=1024, max_files=10)
        .write_bytes("retained", b"other")
    )
    await service.purge()
    assert storage.files == {f"conversations/{OTHER}/exports/retained": b"other"}


async def test_uncertain_remote_result_survives_restart_and_never_expires(database):
    cp, runtime = database
    await _migrate(runtime)

    class UncertainFilesystem(_MemoryFilesystem):
        async def write(self, path, data):
            await super().write(path, data)
            raise TimeoutError("Remote result is unknown")

    storage = UncertainFilesystem()
    service = ConversationFilesystemService(
        storage, SESSION, fence=SessionFence(runtime)
    )
    with pytest.raises(ConversationScratchpadStorageError):
        await service.scratchpad().write_text("note", "private")
    # Dispose all pooled connections, as after runtime restart. No lease expires.
    await runtime.dispose()
    for _ in range(2):
        with pytest.raises(SessionWritesPending):
            await SessionFence(runtime).close(SESSION)
        with pytest.raises(IntegrityError):
            await _delete_root(cp)
    assert storage.files


async def test_writer_and_close_serialize_at_first_operation(database):
    _, runtime = database
    await _migrate(runtime)
    first, second = SessionFence(runtime), SessionFence(runtime)
    results = await asyncio.gather(
        first.begin_filesystem_write(SESSION),
        second.close(SESSION),
        return_exceptions=True,
    )
    token, close = results
    if isinstance(token, str):
        assert isinstance(close, SessionWritesPending)
        await first.end_filesystem_write(token)
    else:
        assert isinstance(token, SessionPurgedError)
        assert close is None
    await second.close(SESSION)
    await second.acknowledge_purge(SESSION)
    with pytest.raises(SessionPurgedError):
        await first.begin_filesystem_write(SESSION)


async def test_conversion_keeps_tempfiles_owned_until_cleanup_even_if_caller_cancels(
    database, monkeypatch, tmp_path
):
    import tempfile
    import threading

    from fred_core.conversion import office_pdf

    cp, runtime = database
    await _migrate(runtime)
    entered, release = threading.Event(), threading.Event()
    paths = []

    def convert(source_path, **kwargs):
        assert kwargs["strict_cleanup"] is True
        paths.append(source_path)
        entered.set()
        assert release.wait(timeout=10)
        pdf = source_path.with_suffix(".pdf")
        pdf.write_bytes(b"private-pdf")
        return pdf

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(office_pdf, "convert_office_file_to_pdf", convert)
    fence = SessionFence(runtime)
    service = ConversationFilesystemService(_MemoryFilesystem(), SESSION, fence=fence)
    caller = asyncio.create_task(
        service.convert_office_to_pdf(b"private-pptx", suffix=".pptx")
    )
    assert await asyncio.to_thread(entered.wait, 5)
    assert paths[0].read_bytes() == b"private-pptx"
    caller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await caller
    with pytest.raises(SessionWritesPending):
        await SessionFence(runtime).close(SESSION)
    with pytest.raises(IntegrityError):
        await _delete_root(cp)
    release.set()
    await asyncio.gather(*tuple(_FILESYSTEM_WRITES))
    assert not paths[0].parent.exists()
    await fence.close(SESSION)
    await fence.acknowledge_purge(SESSION)
    await _delete_root(cp)
    with pytest.raises(IntegrityError):
        await service.convert_office_to_pdf(b"late-private", suffix=".pptx")
    assert len(paths) == 1


async def test_conversion_cleanup_failure_remains_pending(database, monkeypatch):
    from fred_core.conversion import office_pdf

    cp, runtime = database
    await _migrate(runtime)

    async def uncertain(*args, **kwargs):
        assert kwargs["strict_cleanup"] is True
        raise OSError("Temporary-file cleanup incomplete")

    monkeypatch.setattr(office_pdf, "convert_office_bytes_to_pdf", uncertain)
    service = ConversationFilesystemService(
        _MemoryFilesystem(), SESSION, fence=SessionFence(runtime)
    )
    with pytest.raises(OSError):
        await service.convert_office_to_pdf(b"private", suffix=".pptx")
    await runtime.dispose()
    with pytest.raises(SessionWritesPending):
        await SessionFence(runtime).close(SESSION)
    with pytest.raises(IntegrityError):
        await _delete_root(cp)
