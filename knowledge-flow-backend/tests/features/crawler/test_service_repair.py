from types import SimpleNamespace

import pytest
from fred_core import KeycloakUser
from fred_core.security.models import AuthorizationError

from knowledge_flow_backend.features.crawler.controller import ui_status_for_run
from knowledge_flow_backend.features.crawler.service import CrawlExecutor, crawler_ingestion_source_tag
from knowledge_flow_backend.features.crawler.structures import CrawlPageVersion, CrawlRun, CrawlStatus, ProcessingProfile
from knowledge_flow_backend.features.metadata.service import MetadataNotFound


def _user() -> KeycloakUser:
    """
    Build a minimal authenticated user for crawler service tests.

    Why this exists:
    - crawler repair paths require a concrete user object for metadata/tag
      operations, but the tests must stay offline and lightweight.

    How to use:
    - call from async crawler unit tests that exercise metadata interactions.
    """
    return KeycloakUser(uid="user-1", username="user", email="user@example.com", roles=["admin"], groups=["admins"])


@pytest.mark.asyncio
async def test_ensure_document_for_page_repairs_existing_page_without_document_uid():
    """
    Ingest a document when a stored page exists but was never linked to one.

    Why this exists:
    - old crawler rows missing `document_uid` must become reusable on reruns.

    How to use:
    - the test bypasses the heavy executor constructor and stubs the repair
      dependencies directly.
    """
    repaired_pages: list[CrawlPageVersion] = []

    async def fake_ingest_markdown_page(**kwargs):
        return SimpleNamespace(document_uid="doc-42")

    async def fake_update_page_version(page: CrawlPageVersion):
        repaired_pages.append(page)
        return page

    executor = object.__new__(CrawlExecutor)
    executor.store = SimpleNamespace(update_page_version=fake_update_page_version)
    executor.metadata_service = SimpleNamespace(get_document_metadata=None, add_tag_id_to_document=None)
    executor.ingest_markdown_page = fake_ingest_markdown_page

    page = CrawlPageVersion(
        id="page-1",
        run_id="run-1",
        normalized_url="https://example.com/page",
        content_hash="hash-1",
        markdown="# Example",
        extracted_text="Example",
    )

    document_uid = await executor.ensure_document_for_page(
        user=_user(),
        directory_tag_id="tag-1",
        profile=ProcessingProfile.FAST,
        page=page,
        existing_page=page,
    )

    assert document_uid == "doc-42"
    assert [entry.document_uid for entry in repaired_pages] == ["doc-42"]


@pytest.mark.asyncio
async def test_ensure_document_for_page_reuses_existing_document_and_adds_missing_tag():
    """
    Reuse an existing crawled document instead of ingesting a duplicate.

    Why this exists:
    - repeated crawls of the same page should attach the existing document to
      the requested directory when the page version already has a document UID.

    How to use:
    - the test stubs metadata service calls and asserts no new ingestion runs.
    """
    add_tag_calls: list[tuple[str, str]] = []

    async def fake_get_document_metadata(user, document_uid):
        return SimpleNamespace(document_uid=document_uid, tags=SimpleNamespace(tag_ids=["tag-existing"]))

    async def fake_add_tag_to_document(user, metadata, new_tag_id):
        add_tag_calls.append((metadata.document_uid, new_tag_id))

    async def fake_ingest_markdown_page(**kwargs):
        raise AssertionError("ingest_markdown_page should not run when a document already exists")

    executor = object.__new__(CrawlExecutor)
    executor.store = SimpleNamespace(update_page_version=None)
    executor.metadata_service = SimpleNamespace(
        get_document_metadata=fake_get_document_metadata,
        add_tag_id_to_document=fake_add_tag_to_document,
    )
    executor.ingest_markdown_page = fake_ingest_markdown_page

    page = CrawlPageVersion(
        id="page-2",
        run_id="run-2",
        normalized_url="https://example.com/page",
        content_hash="hash-2",
        markdown="# Example",
        extracted_text="Example",
        document_uid="doc-existing",
    )

    document_uid = await executor.ensure_document_for_page(
        user=_user(),
        directory_tag_id="tag-target",
        profile=ProcessingProfile.FAST,
        page=page,
        existing_page=page,
    )

    assert document_uid == "doc-existing"
    assert add_tag_calls == [("doc-existing", "tag-target")]


@pytest.mark.asyncio
async def test_ensure_document_for_page_reingests_when_document_uid_points_to_missing_metadata():
    """
    Recreate the document when an old page points to missing metadata.

    Why this exists:
    - crawler repair must heal dangling `document_uid` references left by
      partial historical runs.

    How to use:
    - the test raises `MetadataNotFound` from the metadata service and checks
      that ingestion runs again.
    """
    repaired_pages: list[CrawlPageVersion] = []

    async def fake_get_document_metadata(user, document_uid):
        raise MetadataNotFound(document_uid)

    async def fake_ingest_markdown_page(**kwargs):
        return SimpleNamespace(document_uid="doc-recreated")

    async def fake_update_page_version(page: CrawlPageVersion):
        repaired_pages.append(page)
        return page

    executor = object.__new__(CrawlExecutor)
    executor.store = SimpleNamespace(update_page_version=fake_update_page_version)
    executor.metadata_service = SimpleNamespace(
        get_document_metadata=fake_get_document_metadata,
        add_tag_id_to_document=None,
    )
    executor.ingest_markdown_page = fake_ingest_markdown_page

    page = CrawlPageVersion(
        id="page-3",
        run_id="run-3",
        normalized_url="https://example.com/page",
        content_hash="hash-3",
        markdown="# Example",
        extracted_text="Example",
        document_uid="doc-missing",
    )

    document_uid = await executor.ensure_document_for_page(
        user=_user(),
        directory_tag_id="tag-target",
        profile=ProcessingProfile.FAST,
        page=page,
        existing_page=page,
    )

    assert document_uid == "doc-recreated"
    assert [entry.document_uid for entry in repaired_pages] == ["doc-recreated"]


@pytest.mark.asyncio
async def test_ensure_document_for_page_reingests_when_existing_document_is_not_authorized():
    """
    Recreate the document when an old page points to an unreadable document.

    Why this exists:
    - crawler page-version dedup must not fail the whole crawl when a previous
      run produced a document the current user cannot read through ReBAC.

    How to use:
    - the test raises `AuthorizationError` from metadata lookup and checks that
      the crawler falls back to normal ingestion.
    """
    repaired_pages: list[CrawlPageVersion] = []

    async def fake_get_document_metadata(user, document_uid):
        raise AuthorizationError(f"Not authorized to read document {document_uid}")

    async def fake_ingest_markdown_page(**kwargs):
        return SimpleNamespace(document_uid="doc-reauthorized")

    async def fake_update_page_version(page: CrawlPageVersion):
        repaired_pages.append(page)
        return page

    executor = object.__new__(CrawlExecutor)
    executor.store = SimpleNamespace(update_page_version=fake_update_page_version)
    executor.metadata_service = SimpleNamespace(
        get_document_metadata=fake_get_document_metadata,
        add_tag_id_to_document=None,
    )
    executor.ingest_markdown_page = fake_ingest_markdown_page

    page = CrawlPageVersion(
        id="page-4",
        run_id="run-4",
        normalized_url="https://example.com/page",
        content_hash="hash-4",
        markdown="# Example",
        extracted_text="Example",
        document_uid="doc-forbidden",
    )

    document_uid = await executor.ensure_document_for_page(
        user=_user(),
        directory_tag_id="tag-target",
        profile=ProcessingProfile.FAST,
        page=page,
        existing_page=page,
    )

    assert document_uid == "doc-reauthorized"
    assert [entry.document_uid for entry in repaired_pages] == ["doc-reauthorized"]


@pytest.mark.asyncio
async def test_finalize_run_marks_empty_crawl_as_failed():
    """
    Fail a crawl that finished without creating any document resources.

    Why this exists:
    - the Resources UI must not show `Ready` for a crawl that produced an empty
      folder after exhausting the frontier.

    How to use:
    - stub the store with a run that has zero `document_uids` and assert the
      executor promotes it to `FAILED`.
    """
    persisted: list[tuple[str, CrawlStatus, str | None]] = []
    run = CrawlRun(id="run-empty", source_id="source-1", status=CrawlStatus.RUNNING, failed_count=1)

    async def fake_get_run(run_id: str):
        return run

    async def fake_mark_run_status(*, run_id: str, status: CrawlStatus, error: str | None = None):
        persisted.append((run_id, status, error))
        return run.model_copy(update={"status": status, "error": error})

    executor = object.__new__(CrawlExecutor)
    executor.store = SimpleNamespace(get_run=fake_get_run, mark_run_status=fake_mark_run_status)

    final_run = await executor.finalize_run(run_id="run-empty")

    assert final_run.status == CrawlStatus.FAILED
    assert persisted == [("run-empty", CrawlStatus.FAILED, "Crawl finished without ingesting any documents.")]


def test_ui_status_for_run_requires_documents_for_ready():
    """
    Show `Ready` only for completed runs that actually produced documents.

    Why this exists:
    - the frontend status label should mirror real ingestion success instead of
      trusting the Temporal workflow transport status alone.

    How to use:
    - build minimal `CrawlRun` models and pass them to `ui_status_for_run`.
    """
    completed_empty = CrawlRun(id="run-1", source_id="source-1", status=CrawlStatus.COMPLETED)
    completed_with_docs = CrawlRun(
        id="run-2",
        source_id="source-1",
        status=CrawlStatus.COMPLETED,
        document_uids=["doc-1"],
    )

    assert ui_status_for_run(completed_empty) == "Failed"
    assert ui_status_for_run(completed_with_docs) == "Ready"


def test_crawler_ingestion_source_tag_uses_declared_push_source():
    """
    Keep crawler ingestion aligned with configured Knowledge Flow source tags.

    Why this exists:
    - using an undeclared source tag breaks metadata extraction before any
      crawled page can be ingested.

    How to use:
    - call `crawler_ingestion_source_tag()` before extracting metadata for a
      crawled page.
    """
    assert crawler_ingestion_source_tag() == "fred"
