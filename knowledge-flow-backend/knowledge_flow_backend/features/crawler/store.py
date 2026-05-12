from __future__ import annotations

from datetime import datetime

from fred_core.sql.async_session import make_session_factory, use_session
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from knowledge_flow_backend.features.crawler.models import (
    CrawlPageVersionRow,
    CrawlRunRow,
    CrawlSourceRow,
    CrawlUrlRow,
)
from knowledge_flow_backend.features.crawler.structures import (
    CrawlPageVersion,
    CrawlRun,
    CrawlSource,
    CrawlStatus,
    CrawlUrl,
    CrawlUrlStatus,
    utc_now,
)


class CrawlStore:
    """PostgreSQL/SQLite-backed store for crawl state and extracted pages."""

    def __init__(self, engine: AsyncEngine) -> None:
        """
        Build a crawler persistence facade on the shared Knowledge Flow SQL engine.

        Why this exists:
        - website crawling needs durable frontier state so crashes do not lose
          discovered URLs or run counters.

        How to use:
        - instantiate with `ApplicationContext.get_async_sql_engine()` and call
          methods from API handlers, background tasks, or Temporal activities.
        """
        self._sessions = make_session_factory(engine)

    async def save_source(self, source: CrawlSource, session: AsyncSession | None = None) -> CrawlSource:
        """Create or update a crawl source model."""
        async with use_session(self._sessions, session) as s:
            row = await s.get(CrawlSourceRow, source.id)
            if row is None:
                row = CrawlSourceRow(id=source.id)
                s.add(row)
            row.workspace_id = source.workspace_id
            row.name = source.name
            row.status = source.status.value
            row.created_at = source.created_at
            row.doc = source.model_dump(mode="json")
        return source

    async def get_source(self, source_id: str, session: AsyncSession | None = None) -> CrawlSource:
        """Return a crawl source by id."""
        async with use_session(self._sessions, session) as s:
            row = await s.get(CrawlSourceRow, source_id)
        if row is None:
            raise ValueError(f"Crawl source '{source_id}' not found")
        return CrawlSource.model_validate(row.doc)

    async def save_run(self, run: CrawlRun, session: AsyncSession | None = None) -> CrawlRun:
        """Create or update one crawl run and its aggregate counters."""
        async with use_session(self._sessions, session) as s:
            row = await s.get(CrawlRunRow, run.id)
            if row is None:
                row = CrawlRunRow(id=run.id)
                s.add(row)
            row.source_id = run.source_id
            row.status = run.status.value
            row.started_at = run.started_at
            row.finished_at = run.finished_at
            row.doc = run.model_dump(mode="json")
        return run

    async def get_run(self, run_id: str, session: AsyncSession | None = None) -> CrawlRun:
        """Return a crawl run by id."""
        async with use_session(self._sessions, session) as s:
            row = await s.get(CrawlRunRow, run_id)
        if row is None:
            raise ValueError(f"Crawl run '{run_id}' not found")
        return CrawlRun.model_validate(row.doc)

    async def enqueue_url(self, url: CrawlUrl, session: AsyncSession | None = None) -> bool:
        """
        Add one URL to the persistent frontier if it is not already present.

        Why this exists:
        - URL-level deduplication must survive process restarts.

        How to use:
        - pass a normalized `CrawlUrl`; `True` means it was newly enqueued.
        """
        async with use_session(self._sessions, session) as s:
            existing = (
                await s.execute(
                    select(CrawlUrlRow).where(
                        CrawlUrlRow.run_id == url.run_id,
                        CrawlUrlRow.normalized_url == url.normalized_url,
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                return False
            s.add(
                CrawlUrlRow(
                    id=url.id,
                    run_id=url.run_id,
                    normalized_url=url.normalized_url,
                    status=url.status.value,
                    depth=url.depth,
                    next_eligible_at=url.next_eligible_at,
                    doc=url.model_dump(mode="json"),
                )
            )
            return True

    async def reserve_batch(
        self,
        *,
        run_id: str,
        limit: int,
        now: datetime | None = None,
        session: AsyncSession | None = None,
    ) -> list[CrawlUrl]:
        """
        Reserve the next eligible frontier URLs without recursion.

        Why this exists:
        - crawlers need a durable queue lifecycle (`pending` -> `reserved` ->
          terminal state) and bounded batches for worker execution.

        How to use:
        - call with a run id and batch size; returned URLs are already marked
          `reserved`.
        """
        now = now or utc_now()
        async with use_session(self._sessions, session) as s:
            rows = (
                (
                    await s.execute(
                        select(CrawlUrlRow)
                        .where(
                            CrawlUrlRow.run_id == run_id,
                            CrawlUrlRow.status == CrawlUrlStatus.PENDING.value,
                            CrawlUrlRow.next_eligible_at <= now,
                        )
                        .order_by(CrawlUrlRow.depth.asc(), CrawlUrlRow.next_eligible_at.asc())
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )
            reserved: list[CrawlUrl] = []
            for row in rows:
                url = CrawlUrl.model_validate(row.doc).model_copy(update={"status": CrawlUrlStatus.RESERVED})
                row.status = CrawlUrlStatus.RESERVED.value
                row.doc = url.model_dump(mode="json")
                reserved.append(url)
            return reserved

    async def update_url(self, url: CrawlUrl, session: AsyncSession | None = None) -> CrawlUrl:
        """Persist a frontier URL lifecycle update."""
        async with use_session(self._sessions, session) as s:
            row = await s.get(CrawlUrlRow, url.id)
            if row is None:
                raise ValueError(f"Crawl URL '{url.id}' not found")
            row.status = url.status.value
            row.depth = url.depth
            row.next_eligible_at = url.next_eligible_at
            row.doc = url.model_dump(mode="json")
        return url

    async def has_content_hash(self, content_hash: str, session: AsyncSession | None = None) -> bool:
        """Return whether extracted content with this hash already exists."""
        async with use_session(self._sessions, session) as s:
            row = (
                await s.execute(
                    select(CrawlPageVersionRow.id).where(CrawlPageVersionRow.content_hash == content_hash).limit(1)
                )
            ).scalar_one_or_none()
        return row is not None

    async def save_page_version(
        self,
        page: CrawlPageVersion,
        session: AsyncSession | None = None,
    ) -> bool:
        """
        Store one extracted page version if the URL/content pair is new.

        Why this exists:
        - content-hash deduplication keeps re-crawls and mirrored pages from
          re-ingesting duplicate text.

        How to use:
        - `True` means the page version was inserted.
        """
        async with use_session(self._sessions, session) as s:
            existing = (
                await s.execute(
                    select(CrawlPageVersionRow.id).where(
                        CrawlPageVersionRow.normalized_url == page.normalized_url,
                        CrawlPageVersionRow.content_hash == page.content_hash,
                    )
                )
            ).scalar_one_or_none()
            if existing:
                return False
            s.add(
                CrawlPageVersionRow(
                    id=page.id,
                    run_id=page.run_id,
                    normalized_url=page.normalized_url,
                    content_hash=page.content_hash,
                    fetched_at=page.fetched_at,
                    markdown=page.markdown,
                    extracted_text=page.extracted_text,
                    doc=page.model_dump(mode="json"),
                )
            )
            return True

    async def get_page_version(
        self,
        *,
        normalized_url: str,
        content_hash: str,
        session: AsyncSession | None = None,
    ) -> CrawlPageVersion | None:
        """
        Return one stored page version by normalized URL and content hash.

        Why this exists:
        - crawler reruns need to reuse or repair existing extracted pages
          instead of treating previously seen content as a hard stop.

        How to use:
        - call before ingesting a page to determine whether a reusable
          `document_uid` is already associated with that exact page version.

        Example:
        - `page = await store.get_page_version(normalized_url=url, content_hash=hash_)`
        """
        async with use_session(self._sessions, session) as s:
            row = (
                await s.execute(
                    select(CrawlPageVersionRow).where(
                        CrawlPageVersionRow.normalized_url == normalized_url,
                        CrawlPageVersionRow.content_hash == content_hash,
                    )
                )
            ).scalar_one_or_none()
        return CrawlPageVersion.model_validate(row.doc) if row else None

    async def update_page_version(
        self,
        page: CrawlPageVersion,
        session: AsyncSession | None = None,
    ) -> CrawlPageVersion:
        """
        Persist changes to an existing page version.

        Why this exists:
        - ingestion repair needs to backfill `document_uid` on previously saved
          crawl pages once a document is finally created.

        How to use:
        - call with a `CrawlPageVersion` that already exists in storage.

        Example:
        - `await store.update_page_version(page.model_copy(update={"document_uid": uid}))`
        """
        async with use_session(self._sessions, session) as s:
            row = await s.get(CrawlPageVersionRow, page.id)
            if row is None:
                raise ValueError(f"Crawl page version '{page.id}' not found")
            row.run_id = page.run_id
            row.normalized_url = page.normalized_url
            row.content_hash = page.content_hash
            row.fetched_at = page.fetched_at
            row.markdown = page.markdown
            row.extracted_text = page.extracted_text
            row.doc = page.model_dump(mode="json")
        return page

    async def has_pending_urls(self, run_id: str, session: AsyncSession | None = None) -> bool:
        """Return whether a run still has pending or reserved frontier URLs."""
        async with use_session(self._sessions, session) as s:
            count = (
                await s.execute(
                    select(func.count()).select_from(CrawlUrlRow).where(
                        CrawlUrlRow.run_id == run_id,
                        CrawlUrlRow.status.in_([CrawlUrlStatus.PENDING.value, CrawlUrlStatus.RESERVED.value]),
                    )
                )
            ).scalar_one()
        return int(count or 0) > 0

    async def mark_run_status(
        self,
        *,
        run_id: str,
        status: CrawlStatus,
        error: str | None = None,
    ) -> CrawlRun:
        """Update a run status and terminal timestamp using one shared path."""
        run = await self.get_run(run_id)
        update = {"status": status, "error": error}
        if status == CrawlStatus.RUNNING and run.started_at is None:
            update["started_at"] = utc_now()
        if status in {CrawlStatus.COMPLETED, CrawlStatus.FAILED}:
            update["finished_at"] = utc_now()
        run = run.model_copy(update=update)
        return await self.save_run(run)
