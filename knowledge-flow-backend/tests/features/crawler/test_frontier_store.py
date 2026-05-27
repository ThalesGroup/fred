from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine

from knowledge_flow_backend.features.crawler.store import CrawlStore
from knowledge_flow_backend.features.crawler.structures import CrawlPageVersion, CrawlRun, CrawlSource, CrawlUrl, CrawlUrlStatus
from knowledge_flow_backend.models.base import Base


@pytest_asyncio.fixture()
async def crawl_store():
    """
    Build an isolated SQLite crawler store.

    Why this exists:
    - frontier tests must stay offline and avoid Postgres/Temporal services.

    How to use:
    - depend on this fixture from async crawler store tests.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield CrawlStore(engine)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_frontier_enqueue_deduplicates_and_reserves(crawl_store: CrawlStore):
    source = await crawl_store.save_source(
        CrawlSource(
            id=str(uuid4()),
            workspace_id="tag-1",
            name="Docs",
            seed_urls=["https://example.com"],
            allowed_domains=["example.com"],
            max_depth=1,
            max_pages=10,
        )
    )
    run = await crawl_store.save_run(CrawlRun(id=str(uuid4()), source_id=source.id))
    url = CrawlUrl(
        id=str(uuid4()),
        run_id=run.id,
        normalized_url="https://example.com/",
        original_url="https://example.com/",
    )

    assert await crawl_store.enqueue_url(url)
    assert not await crawl_store.enqueue_url(url.model_copy(update={"id": str(uuid4())}))

    batch = await crawl_store.reserve_batch(run_id=run.id, limit=10)

    assert [item.normalized_url for item in batch] == ["https://example.com/"]
    assert batch[0].status == CrawlUrlStatus.RESERVED
    assert not await crawl_store.reserve_batch(run_id=run.id, limit=10)


@pytest.mark.asyncio
async def test_page_version_can_be_loaded_and_updated(crawl_store: CrawlStore):
    """
    Ensure stored crawl pages can be repaired with a document UID later.

    Why this exists:
    - crawler reruns need to backfill `document_uid` on already-saved page
      versions once ingestion succeeds.

    How to use:
    - store a page version, reload it by URL/hash, then persist an updated copy.
    """
    page = CrawlPageVersion(
        id=str(uuid4()),
        run_id=str(uuid4()),
        normalized_url="https://example.com/page",
        content_hash="hash-1",
        markdown="# Example",
        extracted_text="Example",
    )

    assert await crawl_store.save_page_version(page)

    loaded = await crawl_store.get_page_version(normalized_url=page.normalized_url, content_hash=page.content_hash)

    assert loaded is not None
    assert loaded.document_uid is None

    updated = loaded.model_copy(update={"document_uid": "doc-1"})
    await crawl_store.update_page_version(updated)

    repaired = await crawl_store.get_page_version(normalized_url=page.normalized_url, content_hash=page.content_hash)

    assert repaired is not None
    assert repaired.document_uid == "doc-1"
