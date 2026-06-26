from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fred_core import Action, KeycloakUser, Resource, authorize_or_raise, get_current_user
from fred_core.scheduler import SchedulerBackend, TemporalClientProvider

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.features.crawler.service import CrawlExecutor, build_initial_source
from knowledge_flow_backend.features.crawler.store import CrawlStore
from knowledge_flow_backend.features.crawler.structures import (
    CrawlRun,
    CrawlRunStatusResponse,
    CrawlSiteRequest,
    CrawlSiteResponse,
    CrawlStatus,
    CrawlUrl,
    ProcessingProfile,
)
from knowledge_flow_backend.features.tag.structure import TagCreate, TagType
from knowledge_flow_backend.features.tag.tag_service import TagService

logger = logging.getLogger(__name__)


def ui_status_for_run(run: CrawlRun) -> str:
    """
    Map crawler status to the Resources UI label.

    Why this exists:
    - the backend owns crawler state while the frontend expects product-facing
      resource labels.

    How to use:
    - call before returning run status to the UI.

    Example:
    - `ui_status_for_run(run)` returns `Ready` only when documents exist.
    """
    if run.status == CrawlStatus.COMPLETED and run.document_uids:
        return "Ready"
    if run.status == CrawlStatus.FAILED or not run.document_uids:
        return "Failed"
    return "Crawling in progress"


class CrawlSiteController:
    """HTTP endpoints for website crawl resources."""

    def __init__(self, router: APIRouter) -> None:
        """
        Register crawl endpoints on the Knowledge Flow API router.

        Why this exists:
        - website crawling is an ingestion connector and belongs beside document
          ingestion/resources in Knowledge Flow.

        How to use:
        - instantiate from `main.py` with the application router.
        """
        self._store: CrawlStore | None = None
        self._tag_service: TagService | None = None
        self._register_routes(router)

    @property
    def store(self) -> CrawlStore:
        """
        Lazily return the crawler store.

        Why this exists:
        - app construction tests and deployments can initialize routers before
          SQL-backed stores are available.

        How to use:
        - access `self.store` inside request/background execution paths.
        """
        if self._store is None:
            self._store = CrawlStore(ApplicationContext.get_instance().get_async_sql_engine())
        return self._store

    @property
    def tag_service(self) -> TagService:
        """
        Lazily return the tag service used for directory handling.

        Why this exists:
        - directory creation is needed only when a crawl starts, not when the
          FastAPI app is assembled.

        How to use:
        - access `self.tag_service` in endpoint handlers.
        """
        if self._tag_service is None:
            self._tag_service = TagService()
        return self._tag_service

    async def _ensure_directory_tag(self, *, user: KeycloakUser, directory_name: str) -> str:
        """
        Create or reuse a document library tag for crawled pages.

        Why this exists:
        - the Resources UI organizes documents by document tags, so crawl output
          must attach to a real library directory.

        How to use:
        - call during crawl start and pass the returned tag id to ingestion.
        """
        tags = await self.tag_service.list_all_tags_for_user(user, tag_type=TagType.DOCUMENT, limit=10000)
        for tag in tags:
            if tag.full_path == directory_name:
                return tag.id
        created = await self.tag_service.create_tag_for_user(
            TagCreate(name=directory_name, path=None, description="Website crawl output", type=TagType.DOCUMENT),
            user,
        )
        return created.id

    async def _run_background_crawl(
        self,
        *,
        run_id: str,
        user: KeycloakUser,
        directory_tag_id: str,
        profile: ProcessingProfile,
    ) -> None:
        """
        Execute a crawl in FastAPI background tasks when no external worker is used.

        Why this exists:
        - local/offline defaults must work with zero third-party services running.

        How to use:
        - schedule via `BackgroundTasks.add_task`.
        """
        try:
            await CrawlExecutor(self.store).run(
                run_id=run_id,
                user=user,
                directory_tag_id=directory_tag_id,
                profile=profile,
            )
        except Exception as exc:
            logger.exception("[CRAWLER] run_id=%s failed", run_id, exc_info=True)
            run = await self.store.mark_run_status(run_id=run_id, status=CrawlStatus.FAILED, error=f"{type(exc).__name__}: {exc}")
            source = await self.store.get_source(run.source_id)
            await self.store.save_source(source.model_copy(update={"status": CrawlStatus.FAILED}))

    async def _start_crawl_execution(
        self,
        *,
        background_tasks: BackgroundTasks,
        run_id: str,
        user: KeycloakUser,
        directory_tag_id: str,
        profile: ProcessingProfile,
    ) -> None:
        """
        Start crawl execution on Temporal when configured, otherwise locally.

        Why this exists:
        - production deployments use the existing worker system, while default
          offline validation must still work without Temporal.

        How to use:
        - call after persisting the run and seed frontier URLs.
        """
        context = ApplicationContext.get_instance()
        if context.get_scheduler_backend() == SchedulerBackend.TEMPORAL:
            from knowledge_flow_backend.features.scheduler.workflow import CrawlSiteWorkflow

            client = await TemporalClientProvider(context.get_config().scheduler.temporal).get_client()
            await client.start_workflow(
                CrawlSiteWorkflow.run,
                args=[run_id, user, directory_tag_id, profile.value],
                id=f"crawl-site-{run_id}",
                task_queue=context.get_config().scheduler.temporal.task_queue,
            )
            return
        background_tasks.add_task(
            self._run_background_crawl,
            run_id=run_id,
            user=user,
            directory_tag_id=directory_tag_id,
            profile=profile,
        )

    def _register_routes(self, router: APIRouter) -> None:
        @router.post(
            "/resources/crawl-site",
            tags=["Resources"],
            response_model=CrawlSiteResponse,
            summary="Crawl a website and ingest extracted pages as document resources.",
        )
        async def crawl_site(
            payload: CrawlSiteRequest,
            background_tasks: BackgroundTasks,
            user: KeycloakUser = Depends(get_current_user),
        ) -> CrawlSiteResponse:
            authorize_or_raise(user, Action.CREATE, Resource.DOCUMENTS)
            try:
                directory_tag_id = await self._ensure_directory_tag(user=user, directory_name=payload.directory_name)
                source = build_initial_source(
                    workspace_id=directory_tag_id,
                    name=payload.directory_name,
                    seed_url=str(payload.site_url),
                    max_depth=payload.max_depth,
                    max_pages=payload.max_pages,
                    restrict_to_domain=payload.restrict_to_domain,
                    respect_robots_txt=payload.respect_robots_txt,
                )
                await self.store.save_source(source)
                run = CrawlRun(id=str(uuid4()), source_id=source.id)
                await self.store.save_run(run)
                for seed in source.seed_urls:
                    await self.store.enqueue_url(
                        CrawlUrl(
                            id=str(uuid4()),
                            run_id=run.id,
                            normalized_url=seed,
                            original_url=seed,
                        )
                    )
                await self._start_crawl_execution(
                    background_tasks=background_tasks,
                    run_id=run.id,
                    user=user,
                    directory_tag_id=directory_tag_id,
                    profile=payload.processing_profile,
                )
                run = run.model_copy(update={"status": CrawlStatus.RUNNING})
                await self.store.save_run(run)
                return CrawlSiteResponse(
                    resource={
                        "id": directory_tag_id,
                        "name": payload.directory_name,
                        "type": "document_directory",
                        "status": ui_status_for_run(run),
                    },
                    run=run,
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            except Exception as exc:
                logger.exception("[CRAWLER] failed to start crawl", exc_info=True)
                raise HTTPException(status_code=500, detail=f"Failed to start crawl: {exc}") from exc

        @router.get(
            "/resources/crawl-site/{run_id}",
            tags=["Resources"],
            response_model=CrawlRunStatusResponse,
            summary="Get website crawl run status.",
        )
        async def get_crawl_run_status(
            run_id: str,
            user: KeycloakUser = Depends(get_current_user),
        ) -> CrawlRunStatusResponse:
            authorize_or_raise(user, Action.READ, Resource.DOCUMENTS)
            try:
                run = await self.store.get_run(run_id)
                return CrawlRunStatusResponse(run=run, ui_status=ui_status_for_run(run))
            except ValueError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
