from __future__ import annotations

from fred_core import KeycloakUser
from temporalio import activity

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.features.crawler.service import CrawlExecutor
from knowledge_flow_backend.features.crawler.store import CrawlStore
from knowledge_flow_backend.features.crawler.structures import CrawlStatus, ProcessingProfile


def coerce_temporal_user(user: KeycloakUser | dict) -> KeycloakUser:
    """
    Rebuild a `KeycloakUser` from Temporal activity input when needed.

    Why this exists:
    - Temporal serializes workflow arguments, so a `KeycloakUser` often arrives
      in activities as a plain dict instead of the original model instance.
    - Authorized service methods require a real `KeycloakUser`.

    How to use:
    - call at the activity boundary before invoking any `@authorize` service.

    Example:
    - `typed_user = coerce_temporal_user(user)`
    """
    if isinstance(user, KeycloakUser):
        return user
    return KeycloakUser.model_validate(user)


@activity.defn
async def crawl_site_run(run_id: str, user, directory_tag_id: str, profile: str) -> dict:
    """
    Temporal activity that executes one website crawl.

    Why this exists:
    - production deployments should run long crawls on the existing Knowledge
      Flow worker instead of tying execution to an API process.

    How to use:
    - the `CrawlSiteWorkflow` invokes this activity with the persisted run id.
    """
    store = CrawlStore(ApplicationContext.get_instance().get_async_sql_engine())
    typed_user = coerce_temporal_user(user)
    try:
        run = await CrawlExecutor(store).run(
            run_id=run_id,
            user=typed_user,
            directory_tag_id=directory_tag_id,
            profile=ProcessingProfile(profile),
        )
        return run.model_dump(mode="json")
    except Exception as exc:
        activity.logger.exception("[CRAWLER] Temporal crawl activity failed run_id=%s", run_id, exc_info=True)
        run = await store.mark_run_status(run_id=run_id, status=CrawlStatus.FAILED, error=f"{type(exc).__name__}: {exc}")
        source = await store.get_source(run.source_id)
        await store.save_source(source.model_copy(update={"status": CrawlStatus.FAILED}))
        raise
