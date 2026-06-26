from types import SimpleNamespace

import pytest
from fred_core import KeycloakUser

from knowledge_flow_backend.features.crawler import activities
from knowledge_flow_backend.features.crawler.activities import coerce_temporal_user
from knowledge_flow_backend.features.crawler.structures import CrawlRun, CrawlStatus


def test_coerce_temporal_user_rebuilds_keycloak_user_from_dict():
    """
    Ensure Temporal JSON payloads become real `KeycloakUser` instances.

    Why this exists:
    - crawler activities receive serialized workflow arguments, and authorized
      service methods require the real Pydantic user model.

    How to use:
    - pass the decoded activity payload and expect a `KeycloakUser`.
    """
    user = coerce_temporal_user(
        {
            "uid": "user-1",
            "username": "alice",
            "roles": ["admin"],
            "email": "alice@app.com",
            "groups": ["/team"],
        }
    )

    assert isinstance(user, KeycloakUser)
    assert user.uid == "user-1"


@pytest.mark.asyncio
async def test_crawl_site_run_marks_run_failed_and_reraises(monkeypatch):
    """
    Ensure Temporal records a real failed activity for crawl errors.

    Why this exists:
    - returning a failed run payload made Temporal show `completed` even when
      the crawl had actually crashed before ingesting anything.

    How to use:
    - patch the executor to raise and assert the activity re-raises after
      persisting failed run/source state.
    """
    failed_runs: list[tuple[str, CrawlStatus, str | None]] = []
    saved_source_statuses: list[CrawlStatus] = []

    class FakeExecutor:
        def __init__(self, store):
            self.store = store

        async def run(self, **kwargs):
            raise RuntimeError("boom")

    class FakeStore:
        async def mark_run_status(self, *, run_id: str, status: CrawlStatus, error: str | None = None):
            failed_runs.append((run_id, status, error))
            return CrawlRun(id=run_id, source_id="source-1", status=status, error=error)

        async def get_source(self, source_id: str):
            return SimpleNamespace(
                id=source_id,
                status=CrawlStatus.RUNNING,
                model_copy=lambda update: SimpleNamespace(status=update["status"]),
            )

        async def save_source(self, source):
            saved_source_statuses.append(source.status)
            return source

    monkeypatch.setattr(activities, "CrawlStore", lambda engine: FakeStore())
    monkeypatch.setattr(activities, "CrawlExecutor", FakeExecutor)
    monkeypatch.setattr(
        activities.ApplicationContext,
        "get_instance",
        lambda: SimpleNamespace(get_async_sql_engine=lambda: object()),
    )

    with pytest.raises(RuntimeError, match="boom"):
        await activities.crawl_site_run(
            "run-1",
            {"uid": "user-1", "username": "alice", "roles": ["admin"], "email": "alice@app.com", "groups": []},
            "tag-1",
            "fast",
        )

    assert failed_runs == [("run-1", CrawlStatus.FAILED, "RuntimeError: boom")]
    assert saved_source_statuses == [CrawlStatus.FAILED]
