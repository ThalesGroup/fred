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

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from temporalio.testing import ActivityEnvironment

from knowledge_flow_backend import application_context
from knowledge_flow_backend.features.ingestion import ingestion_service
from knowledge_flow_backend.features.scheduler import pull_files_activities


def _prepare(monkeypatch, fetch):
    context = Mock()
    context.get_content_loader.return_value.fetch_by_relative_path = fetch
    monkeypatch.setattr(application_context.ApplicationContext, "get_instance", lambda: context)
    metadata = SimpleNamespace(document_uid="doc", source=SimpleNamespace())
    service = SimpleNamespace(extract_metadata=AsyncMock(return_value=metadata), save_metadata=AsyncMock())
    monkeypatch.setattr(ingestion_service, "get_ingestion_service", lambda: service)
    monkeypatch.setattr(pull_files_activities, "emit_temporal_activity_queue_wait_kpi", Mock())
    monkeypatch.setattr(pull_files_activities, "emit_temporal_activity_result_kpis", Mock())
    file = SimpleNamespace(external_path="document.pdf", source_tag="source", processed_by=Mock(), tags=[], profile="medium")
    return file, service, metadata


@pytest.mark.parametrize("temporal", [False, True])
def test_pull_download_leaves_event_loop_available(monkeypatch, temporal):
    async def scenario():
        loop = asyncio.get_running_loop()
        entered = asyncio.Event()
        release = threading.Event()
        callback_progressed = []
        download_paths = []

        def fetch(name, destination):
            def probe():
                callback_progressed.append(True)
                entered.set()
                release.set()

            loop.call_soon_threadsafe(probe)
            # A bounded wait makes the old inline implementation fail instead
            # of hanging the suite: its event loop cannot execute probe().
            assert release.wait(2), "download blocked the event loop"
            path = destination / name
            path.write_bytes(b"test")
            download_paths.append(path)
            return path

        file, service, metadata = _prepare(monkeypatch, fetch)
        environment = ActivityEnvironment()
        heartbeats = []
        environment.on_heartbeat = lambda *details: heartbeats.append(details)
        if temporal:
            result = await environment.run(pull_files_activities.create_pull_file_metadata, file)
        else:
            result = await pull_files_activities.create_pull_file_metadata(file)
        assert entered.is_set() and callback_progressed == [True]
        assert result is metadata
        assert metadata.source.pull_location == file.external_path
        service.save_metadata.assert_awaited_once_with(file.processed_by, metadata=metadata)
        assert len(download_paths) == 1 and not download_paths[0].parent.exists()
        if temporal:
            assert heartbeats
            assert heartbeats[0][0]["stage"] == "pull_metadata_fetch"

    asyncio.run(scenario())


@pytest.mark.parametrize("temporal", [False, True])
def test_pull_download_preserves_error_and_skips_persistence(monkeypatch, temporal):
    error = OSError("source unavailable")
    file, service, _ = _prepare(monkeypatch, Mock(side_effect=error))

    async def scenario():
        with pytest.raises(OSError) as caught:
            if temporal:
                await ActivityEnvironment().run(pull_files_activities.create_pull_file_metadata, file)
            else:
                await pull_files_activities.create_pull_file_metadata(file)
        assert caught.value is error
        service.extract_metadata.assert_not_awaited()
        service.save_metadata.assert_not_awaited()

    asyncio.run(scenario())
