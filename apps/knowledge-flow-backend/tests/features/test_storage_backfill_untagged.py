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

"""#2149 review — the storage backfill must survive untagged documents.

`calculate_ingested_documents_sizes` read `row.author`, but `DocumentMetadataRow`
has no such column, so the reconciliation aborted with `AttributeError` on the
first untagged row — and again on any tag carrying the legacy "personal" owner
sentinel. That matters beyond the crash: the backfill is the documented remedy
for drifted counters, so a deployment holding one untagged document had no way
to run it.

Conversation attachments have no corpus folder and do not consume corpus quotas.
Canonical SQL folder owners determine every corpus document’s storage account.
"""

import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import pytest

_BACKFILL = pathlib.Path(__file__).resolve().parents[2] / "alembic" / "backfill" / "backfill_storage_usage.py"


def _load_backfill_module():
    spec = importlib.util.spec_from_file_location("backfill_storage_usage", _BACKFILL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["backfill_storage_usage"] = module
    spec.loader.exec_module(module)
    return module


class _Row:
    """A metadata row as the ORM returns it — deliberately WITHOUT `author`,
    mirroring `DocumentMetadataRow`. Touching `row.author` raises AttributeError,
    which is exactly the production failure."""

    def __init__(self, uid: str, tag_ids: list[str] | None, size: int):
        self.document_uid = uid
        self.folder_id = tag_ids[0] if tag_ids else None
        self.doc = {"file": {"file_size_bytes": size}, "identity": {"author": "Jane Doe"}}


class _Session:
    """`session.get` is used for two different models: TagRow (by tag id) and
    TeamMetadataRow (by owner id, to confirm the owner is a team)."""

    def __init__(self, rows, tags=None, teams=()):
        self._rows = rows
        self._tags = tags or {}
        self._teams = set(teams)

    async def execute(self, _stmt):
        rows = self._rows
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: rows))

    async def get(self, model, key):
        if getattr(model, "__name__", "") == "TeamMetadataRow":
            return SimpleNamespace(id=key) if key in self._teams else None
        return self._tags.get(key)


@pytest.mark.asyncio
async def test_untagged_documents_are_skipped_instead_of_crashing() -> None:
    """The load-bearing case: an untagged row must not abort the run, and must
    not be charged to anyone."""
    module = _load_backfill_module()
    session = _Session([_Row("doc-untagged", [], 4096)])

    user_sizes, team_sizes = await module.calculate_ingested_documents_sizes(session)

    assert user_sizes == {}
    assert team_sizes == {}


@pytest.mark.asyncio
async def test_a_legacy_personal_owner_sentinel_refuses_to_run() -> None:
    """Second crash site, and it must not degrade into a silent wrong answer.

    Both runtime and migration require canonical team owners. Because this script
    writes absolute counters, missing ownership must abort without writing totals.
    """
    module = _load_backfill_module()
    session = _Session(
        [_Row("doc-personal", ["tag-legacy"], 2048)],
        tags={"tag-legacy": SimpleNamespace(tag_id="tag-legacy", owner_id="personal")},
    )

    with pytest.raises(RuntimeError) as exc:
        await module.calculate_ingested_documents_sizes(session)

    assert "tag-legacy" in str(exc.value)
    assert "absolute" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_untagged_rows_do_not_stop_tagged_rows_from_being_counted() -> None:
    """Regression guard: the crash aborted the whole reconciliation, so tagged
    documents after an untagged one were never counted either."""
    module = _load_backfill_module()
    session = _Session(
        [_Row("doc-untagged", [], 4096), _Row("doc-team", ["tag-team"], 1024)],
        tags={"tag-team": SimpleNamespace(tag_id="tag-team", owner_id="team-a")},
        teams=["team-a"],
    )

    _user_sizes, team_sizes = await module.calculate_ingested_documents_sizes(session)

    assert team_sizes.get("team-a") == 1024
