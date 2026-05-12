from __future__ import annotations

import hashlib
import logging
import pathlib
import re
import tempfile
from datetime import timedelta
from uuid import uuid4

import httpx
from fred_core import KeycloakUser
from fred_core.security.models import AuthorizationError

from knowledge_flow_backend.common.document_structures import (
    DocumentMetadata,
    FileType,
    SourceType,
)
from knowledge_flow_backend.common.structures import IngestionProcessingProfile
from knowledge_flow_backend.features.crawler.extractor import extract_html
from knowledge_flow_backend.features.crawler.fetcher import HostRateLimiter, HttpFetcher
from knowledge_flow_backend.features.crawler.robots import RobotsCache
from knowledge_flow_backend.features.crawler.store import CrawlStore
from knowledge_flow_backend.features.crawler.structures import (
    CrawlPageVersion,
    CrawlRun,
    CrawlSource,
    CrawlStatus,
    CrawlUrl,
    CrawlUrlStatus,
    ProcessingProfile,
    utc_now,
)
from knowledge_flow_backend.features.crawler.url_utils import is_allowed_scope, normalize_url, url_host
from knowledge_flow_backend.features.ingestion.ingestion_service import get_ingestion_service
from knowledge_flow_backend.features.metadata.service import MetadataNotFound, MetadataService

logger = logging.getLogger(__name__)
CRAWLER_INGESTION_SOURCE_TAG = "fred"


def content_hash(text: str) -> str:
    """
    Return the SHA-256 hash used for crawler content deduplication.

    Why this exists:
    - duplicate pages and re-crawls should not produce duplicate Knowledge Flow
      documents or vectors.

    How to use:
    - pass extracted Markdown or text after normalization.

    Example:
    - `fingerprint = content_hash(markdown)`
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def safe_page_filename(title: str | None, url: str) -> str:
    """
    Build a stable Markdown filename for an extracted page.

    Why this exists:
    - the ingestion pipeline expects file-like inputs and document names, while
      crawled URLs can contain characters that are awkward in filenames.

    How to use:
    - pass the extracted page title and normalized URL.
    """
    base = title or url
    base = re.sub(r"[^A-Za-z0-9._ -]+", "-", base).strip(" .-")[:80] or "page"
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:10]
    return f"{base}-{digest}.md"


def crawler_ingestion_source_tag() -> str:
    """
    Return the configured document source tag used for crawled page ingestion.

    Why this exists:
    - the ingestion pipeline only accepts source tags declared in
      `config.document_sources`, and crawled pages should reuse the standard
      push-source contract instead of inventing an undeclared tag.

    How to use:
    - call before invoking `IngestionService.extract_metadata`.
    - keep crawler-specific provenance in metadata extensions, not in the
      `source_tag` registry key.

    Example:
    - `source_tag = crawler_ingestion_source_tag()`
    """
    return CRAWLER_INGESTION_SOURCE_TAG


class CrawlExecutor:
    """Run a crawl and push extracted pages through Knowledge Flow ingestion."""

    def __init__(self, store: CrawlStore) -> None:
        """
        Build a crawl executor.

        Why this exists:
        - the API and Temporal activity need one shared implementation for
          frontier processing, fetching, extraction, and ingestion handoff.

        How to use:
        - call `run(run_id=..., user=..., directory_tag_id=..., profile=...)`.
        """
        self.store = store
        self.fetcher = HttpFetcher()
        self.rate_limiter = HostRateLimiter()
        self.metadata_service = MetadataService()

    async def finalize_run(self, *, run_id: str) -> CrawlRun:
        """
        Resolve the terminal status for one crawl after frontier processing ends.

        Why this exists:
        - a finished Temporal activity is not enough to declare product success;
          the crawl must have produced at least one ingested document.

        How to use:
        - call once after the main crawl loop drains the frontier.
        - the returned run is already persisted with its final status.

        Example:
        - `final_run = await executor.finalize_run(run_id=run.id)`
        """
        run = await self.store.get_run(run_id)
        if run.document_uids:
            return await self.store.mark_run_status(run_id=run.id, status=CrawlStatus.COMPLETED, error=None)

        error = run.error or "Crawl finished without ingesting any documents."
        return await self.store.mark_run_status(run_id=run.id, status=CrawlStatus.FAILED, error=error)

    async def ingest_markdown_page(
        self,
        *,
        user: KeycloakUser,
        directory_tag_id: str,
        profile: ProcessingProfile,
        page: CrawlPageVersion,
    ) -> DocumentMetadata:
        """
        Convert an extracted page into the existing ingestion pipeline.

        Why this exists:
        - website pages must become normal Knowledge Flow documents and vectors
          without introducing a parallel indexing path.

        How to use:
        - call after `save_page_version`; it writes a temporary Markdown input
          and runs the same input/output processors as uploads.
        """
        ingestion = get_ingestion_service()
        source_tag = crawler_ingestion_source_tag()
        with tempfile.TemporaryDirectory(prefix="crawl-page-") as tmp:
            root = pathlib.Path(tmp)
            input_dir = root / "input"
            output_dir = root / "output"
            input_dir.mkdir(parents=True, exist_ok=True)
            output_dir.mkdir(parents=True, exist_ok=True)
            filename = safe_page_filename(page.title, page.normalized_url)
            input_path = input_dir / filename
            input_path.write_text(page.markdown, encoding="utf-8")

            metadata = await ingestion.extract_metadata(
                user,
                file_path=input_path,
                tags=[directory_tag_id],
                source_tag=source_tag,
                profile=IngestionProcessingProfile(profile.value),
            )
            metadata.identity.title = page.title or page.normalized_url
            metadata.source.source_type = SourceType.PUSH
            metadata.source.source_tag = source_tag
            metadata.source.pull_location = page.normalized_url
            metadata.source.retrievable = False
            metadata.file.file_type = FileType.MD
            metadata.file.mime_type = "text/markdown"
            metadata.file.sha256 = page.content_hash
            metadata.extensions = {
                **(metadata.extensions or {}),
                "crawler": {
                    "run_id": page.run_id,
                    "url": page.normalized_url,
                    "etag": page.etag,
                    "last_modified": page.last_modified,
                },
            }

            ingestion.save_input(user, metadata=metadata, input_dir=input_dir)
            ingestion.process_input(user, input_path=input_path, output_dir=output_dir, metadata=metadata, profile=profile.value)
            ingestion.save_output(user, metadata=metadata, output_dir=output_dir)
            metadata = ingestion.process_output(
                user,
                input_file_name="output.md",
                output_dir=output_dir,
                input_file_metadata=metadata,
                profile=profile.value,
            )
            await ingestion.save_metadata(user, metadata=metadata)
            return metadata

    async def run(
        self,
        *,
        run_id: str,
        user: KeycloakUser,
        directory_tag_id: str,
        profile: ProcessingProfile,
    ) -> CrawlRun:
        """
        Execute one crawl run to completion.

        Why this exists:
        - long-running crawler execution needs one deterministic loop with
          persistent frontier reservation rather than recursion.

        How to use:
        - called by background tasks or Temporal activities using a persisted
          run id.
        """
        run = await self.store.mark_run_status(run_id=run_id, status=CrawlStatus.RUNNING)
        source = await self.store.get_source(run.source_id)
        await self.store.save_source(source.model_copy(update={"status": CrawlStatus.RUNNING}))
        robots = RobotsCache()
        async with httpx.AsyncClient(headers={"user-agent": "FredCrawler/1.0"}) as client:
            while run.extracted_count < source.max_pages:
                batch = await self.store.reserve_batch(run_id=run.id, limit=5)
                if not batch:
                    if not await self.store.has_pending_urls(run.id):
                        break
                    continue
                for frontier_url in batch:
                    if run.extracted_count >= source.max_pages:
                        break
                    await self._process_url(
                        client=client,
                        robots=robots,
                        source=source,
                        run=run,
                        frontier_url=frontier_url,
                        user=user,
                        directory_tag_id=directory_tag_id,
                        profile=profile,
                    )
                    run = await self.store.get_run(run.id)
        final_run = await self.finalize_run(run_id=run.id)
        await self.store.save_source(source.model_copy(update={"status": final_run.status}))
        return final_run

    async def ensure_document_for_page(
        self,
        *,
        user: KeycloakUser,
        directory_tag_id: str,
        profile: ProcessingProfile,
        page: CrawlPageVersion,
        existing_page: CrawlPageVersion | None,
    ) -> str:
        """
        Return a document UID for one extracted page, creating or reusing it.

        Why this exists:
        - a repeated crawl should reuse existing page documents when possible,
          and older crawl rows missing `document_uid` must be repairable.

        How to use:
        - call after resolving whether an identical page version already exists.
        - the method returns the document UID now associated with the page.

        Example:
        - `document_uid = await self.ensure_document_for_page(..., page=page, existing_page=existing)`
        """
        reusable_page = existing_page or page
        if reusable_page.document_uid:
            try:
                metadata = await self.metadata_service.get_document_metadata(user, reusable_page.document_uid)
                if directory_tag_id not in (metadata.tags.tag_ids or []):
                    await self.metadata_service.add_tag_id_to_document(user, metadata, directory_tag_id)
                return metadata.document_uid
            except (AuthorizationError, MetadataNotFound):
                pass

        metadata = await self.ingest_markdown_page(
            user=user,
            directory_tag_id=directory_tag_id,
            profile=profile,
            page=reusable_page,
        )
        persisted_page = reusable_page.model_copy(update={"document_uid": metadata.document_uid})
        if existing_page is None:
            await self.store.update_page_version(persisted_page)
        else:
            await self.store.update_page_version(persisted_page)
        return metadata.document_uid

    async def _process_url(
        self,
        *,
        client: httpx.AsyncClient,
        robots: RobotsCache,
        source: CrawlSource,
        run: CrawlRun,
        frontier_url: CrawlUrl,
        user: KeycloakUser,
        directory_tag_id: str,
        profile: ProcessingProfile,
    ) -> None:
        """
        Process one reserved frontier URL through fetch, extract, enqueue, ingest.

        Why this exists:
        - keeping one URL lifecycle update path makes retries, counters, and
          failure states consistent.

        How to use:
        - only call with URLs returned by `reserve_batch`.
        """
        try:
            if source.respect_robots_txt and not await robots.allowed(client, frontier_url.normalized_url):
                await self.store.update_url(frontier_url.model_copy(update={"status": CrawlUrlStatus.SKIPPED, "error": "blocked by robots.txt"}))
                return
            await self.rate_limiter.wait(frontier_url.normalized_url)
            fetched = await self.fetcher.fetch(client, frontier_url.normalized_url)
            extracted = extract_html(fetched.content, fetched.url)
            fingerprint = content_hash(extracted.markdown)
            page = CrawlPageVersion(
                id=str(uuid4()),
                run_id=run.id,
                normalized_url=frontier_url.normalized_url,
                content_hash=fingerprint,
                markdown=extracted.markdown,
                extracted_text=extracted.text,
                title=extracted.title,
                etag=fetched.etag,
                last_modified=fetched.last_modified,
            )
            existing_page = await self.store.get_page_version(
                normalized_url=page.normalized_url,
                content_hash=page.content_hash,
            )
            inserted = False
            if existing_page is None:
                inserted = await self.store.save_page_version(page)
            document_uids = list(run.document_uids)
            extracted_increment = 0
            if inserted or existing_page is not None:
                document_uid = await self.ensure_document_for_page(
                    user=user,
                    directory_tag_id=directory_tag_id,
                    profile=profile,
                    page=page,
                    existing_page=existing_page,
                )
                if document_uid not in document_uids:
                    document_uids.append(document_uid)
                extracted_increment = 1

            discovered = 0
            if frontier_url.depth < source.max_depth:
                for href in extracted.links:
                    try:
                        normalized = normalize_url(href, fetched.url)
                    except ValueError:
                        continue
                    if not normalized.startswith(("http://", "https://")):
                        continue
                    if not is_allowed_scope(normalized, source.allowed_domains, source.restrict_to_domain):
                        continue
                    added = await self.store.enqueue_url(
                        CrawlUrl(
                            id=str(uuid4()),
                            run_id=run.id,
                            normalized_url=normalized,
                            original_url=href,
                            parent_url=frontier_url.normalized_url,
                            depth=frontier_url.depth + 1,
                        )
                    )
                    if added:
                        discovered += 1

            await self.store.update_url(
                frontier_url.model_copy(
                    update={
                        "status": CrawlUrlStatus.EXTRACTED,
                        "content_fingerprint": fingerprint,
                    }
                )
            )
            await self.store.save_run(
                run.model_copy(
                    update={
                        "discovered_count": run.discovered_count + discovered,
                        "fetched_count": run.fetched_count + 1,
                        "extracted_count": run.extracted_count + extracted_increment,
                        "document_uids": document_uids,
                    }
                )
            )
        except Exception as exc:
            error_message = str(exc)
            retry_count = frontier_url.retry_count + 1
            logger.exception(
                "[CRAWLER] URL processing failed run_id=%s url=%s retry=%s",
                run.id,
                frontier_url.normalized_url,
                retry_count,
                exc_info=True,
            )
            if retry_count < 3:
                await self.store.update_url(
                    frontier_url.model_copy(
                        update={
                            "status": CrawlUrlStatus.PENDING,
                            "retry_count": retry_count,
                            "next_eligible_at": utc_now() + timedelta(seconds=2**retry_count),
                            "error": error_message,
                        }
                    )
                )
            else:
                await self.store.update_url(
                    frontier_url.model_copy(
                        update={
                            "status": CrawlUrlStatus.FAILED,
                            "retry_count": retry_count,
                            "error": error_message,
                        }
                    )
                )
                current_run = await self.store.get_run(run.id)
                run_error = current_run.error or error_message
                await self.store.save_run(
                    current_run.model_copy(
                        update={
                            "failed_count": current_run.failed_count + 1,
                            "error": run_error,
                        }
                    )
                )


def build_initial_source(*, workspace_id: str, name: str, seed_url: str, max_depth: int, max_pages: int, restrict_to_domain: bool, respect_robots_txt: bool) -> CrawlSource:
    """
    Build the persisted source model for a new crawl request.

    Why this exists:
    - API handlers need one small factory that derives allowed domains from the
      normalized seed URL.

    How to use:
    - call after validating the request payload.
    """
    normalized = normalize_url(seed_url)
    return CrawlSource(
        id=str(uuid4()),
        workspace_id=workspace_id,
        name=name,
        seed_urls=[normalized],
        allowed_domains=[url_host(normalized)],
        max_depth=max_depth,
        max_pages=max_pages,
        restrict_to_domain=restrict_to_domain,
        respect_robots_txt=respect_robots_txt,
    )
