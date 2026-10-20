# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed
# under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied.

"""Live folder inventory/removal, including an opt-in truncated-list workload."""

import json
import os
from contextlib import ExitStack
from uuid import uuid4

import pytest
from document_probe import (
    ClientFactory,
    ApiClient,
    checked,
    ingest,
    library,
    wait_indexed,
    wait_until,
)
from factory_config import TEST_TEAM, USERS


def upload_unprocessed(client: ApiClient, tag_id: str, count: int) -> set[str]:
    """Create readable metadata/content without embedding the large background corpus."""
    uids: set[str] = set()
    for start in range(0, count, 50):
        size = min(50, count - start)
        response = checked(
            client.post(
                "/upload-documents",
                files=[
                    (
                        "files",
                        (
                            f"validation-{uuid4().hex}.md",
                            f"Background fixture {uuid4().hex}",
                            "text/markdown",
                        ),
                    )
                    for _ in range(size)
                ],
                data={
                    "metadata_json": json.dumps({"tags": [tag_id], "profile": "fast"})
                },
                timeout=180,
            )
        )
        events = [
            json.loads(line) for line in response.text.splitlines() if line.strip()
        ]
        assert events and events[-1].get("step") == "done", (
            "Incomplete background upload stream"
        )
        assert all(
            e.get("status") not in {"failed", "error", "conflict", "ignored"}
            for e in events
        ), "Background upload failed"
        batch = {e["document_uid"] for e in events if e.get("document_uid")}
        assert len(batch) == size and not batch.intersection(uids), (
            "Background upload returned missing or duplicate UIDs"
        )
        uids.update(batch)
    return uids


@pytest.mark.parametrize(
    "background_count",
    [
        0,
        pytest.param(
            1001,
            marks=pytest.mark.skipif(
                os.getenv("FRED_VALIDATION_LARGE_CORPUS") != "1",
                reason="Set FRED_VALIDATION_LARGE_CORPUS=1 to create 1,001 background documents",
            ),
        ),
    ],
)
def test_folder_inventory_and_last_link_cleanup(
    cp: ClientFactory, kf: ClientFactory, background_count: int
) -> None:
    """A folder lists all its documents and deletion releases metadata, content, vectors and quota (background={background_count})."""
    editor = next(
        name for name, user in USERS.items() if user.is_team_editor_in(TEST_TEAM)
    )
    admin = next(name for name, user in USERS.items() if user.is_platform_admin)
    team = next(
        t for t in checked(cp(editor).get("/teams")).json() if t["name"] == TEST_TEAM
    )
    team_id = team.get("id") or team["team_id"]
    client = kf(editor)

    def snapshot() -> tuple[int, int, int, int]:
        audit = checked(kf(admin).get("/documents/audit", timeout=180)).json()
        current = next(
            t
            for t in checked(cp(editor).get("/teams")).json()
            if t["name"] == TEST_TEAM
        )
        return (
            audit["metadata_count"],
            audit["content_count"],
            audit["vector_count"],
            current["current_resources_storage_size"] or 0,
        )

    with ExitStack() as cleanup:
        background = cleanup.enter_context(library(client, team_id))
        target = cleanup.enter_context(library(client, team_id))
        background_uids = upload_unprocessed(client, background["id"], background_count)
        baseline = snapshot()
        uids = set()
        size_bytes = 0
        for _ in range(20 if background_count else 3):
            marker = f"INVENTORY{uuid4().hex}"
            uid = ingest(client, [target["id"]], marker)
            wait_indexed(
                client, team_id=team_id, library_id=target["id"], uid=uid, marker=marker
            )
            metadata = checked(client.get(f"/documents/metadata/{uid}")).json()
            size_bytes += metadata["file"]["file_size_bytes"]
            uids.add(uid)
        count = len(uids)
        expected = (
            baseline[0] + count,
            baseline[1] + count,
            baseline[2] + count,
            baseline[3] + size_bytes,
        )
        wait_until(
            lambda: snapshot() == expected,
            description="positive store and quota controls (requires an idle deployment)",
            timeout=30,
        )

        folder = checked(client.get(f"/tags/{target['id']}")).json()
        assert set(folder["item_ids"]) == uids
        page = checked(
            client.post(
                "/documents/metadata/browse",
                json={"tag_id": target["id"], "offset": 0, "limit": 50},
            )
        ).json()
        assert page["total"] == count
        assert {d["identity"]["document_uid"] for d in page["documents"]} == uids

        checked(client.delete(f"/tags/{target['id']}", timeout=180))
        assert client.get(f"/tags/{target['id']}").status_code in (403, 404)
        for uid in uids:
            assert client.get(f"/documents/metadata/{uid}").status_code in (403, 404)
        wait_until(
            lambda: snapshot() == baseline,
            description="last-link store cleanup and exact quota release",
            timeout=30,
        )
        # An unrelated folder and all its uploaded documents must survive.
        assert (
            set(checked(client.get(f"/tags/{background['id']}")).json()["item_ids"])
            == background_uids
        )


@pytest.mark.parametrize(
    "background_count",
    [
        0,
        pytest.param(
            3000,
            marks=pytest.mark.skipif(
                os.getenv("FRED_VALIDATION_LARGE_CORPUS") != "1",
                reason="Set FRED_VALIDATION_LARGE_CORPUS=1 to create 3,000 background documents",
            ),
        ),
    ],
)
def test_tabular_workbook_amid_large_readable_corpus(
    cp: ClientFactory, kf: ClientFactory, background_count: int
) -> None:
    """Tabular tools see a team CSV however many documents the caller can read."""
    editor = next(
        name for name, user in USERS.items() if user.is_team_editor_in(TEST_TEAM)
    )
    team = next(
        t for t in checked(cp(editor).get("/teams")).json() if t["name"] == TEST_TEAM
    )
    team_id = team.get("id") or team["team_id"]
    client = kf(editor)

    with ExitStack() as cleanup:
        background = cleanup.enter_context(library(client, team_id))
        target = cleanup.enter_context(library(client, team_id))
        upload_unprocessed(client, background["id"], background_count)
        uid = ingest(
            client,
            [target["id"]],
            "",
            file=(f"validation-{uuid4().hex}.csv", "city,amount\nParis,10\nLyon,20\n", "text/csv"),
        )
        scope = {"owner_filter": "team", "team_id": team_id}

        def listed(params: dict) -> set[str]:
            documents = checked(client.get("/tabular/documents", params=params, timeout=180)).json()
            return {d["document_uid"] for d in documents}

        wait_until(lambda: uid in listed(scope), description="tabular indexing", timeout=180)
        assert uid in listed({}), "Unscoped discovery must also see the workbook"

        [description] = checked(
            client.get(
                "/tabular/documents/schemas",
                params={"document_uids": uid, **scope},
                timeout=180,
            )
        ).json()
        alias = description["tables"][0]["query_alias"]
        result = checked(
            client.post(
                "/tabular/query",
                json={"sql": f'SELECT SUM(amount) AS total FROM "{alias}"', "dataset_uids": [uid], **scope},
                timeout=180,
            )
        ).json()
        assert result["rows"] == [{"total": 30}]
        found = checked(
            client.post(
                "/tabular/search",
                json={"keyword": "Lyon", "dataset_uids": [uid], **scope},
                timeout=180,
            )
        ).json()
        assert [match["document_uid"] for match in found["matches"]] == [uid]
