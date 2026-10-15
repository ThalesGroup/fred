# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed
# under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied.

"""Offline validation of the opt-in corpus upload protocol."""

import json
import httpx
import pytest
from scenarios.test_folder_inventory import upload_unprocessed


@pytest.mark.parametrize(
    "fault", [None, "missing", "failed", "unfinished", "duplicate"]
)
def test_background_upload_validates_every_batch(fault):
    calls = []

    def handler(request):
        assert request.url.path == "/upload-documents"
        calls.append(request)
        batch_size = 50 if len(calls) == 1 else 1
        uids = [f"d-{len(calls)}-{i}" for i in range(batch_size)]
        if fault == "missing":
            uids.pop()
        if fault == "duplicate" and len(calls) == 2:
            uids = ["d-1-0"]
        events = [{"status": "success", "document_uid": uid} for uid in uids]
        if fault != "unfinished":
            events.append(
                {"step": "done", "status": "failed" if fault == "failed" else "success"}
            )
        return httpx.Response(200, text="\n".join(json.dumps(e) for e in events))

    with httpx.Client(
        base_url="https://fixture.invalid", transport=httpx.MockTransport(handler)
    ) as client:
        if fault:
            with pytest.raises(AssertionError):
                upload_unprocessed(client, "tag", 51)
        else:
            assert len(upload_unprocessed(client, "tag", 51)) == 51
            assert len(calls) == 2
