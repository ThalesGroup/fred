from __future__ import annotations

import logging
from pathlib import Path

from fred_core import (
    BaseSessionStore,
    PostgresSessionStore,
    RebacEngine,
    rebac_factory,
)
from fred_core.scheduler import (
    SchedulerBackend,
    TemporalClientProvider,
    resolve_scheduler_backend,
)
from fred_core.sql import create_async_engine_from_config
from fred_core.store import ContentStore, LocalContentStore, MinioContentStore
from fred_core.tasks.service import TaskService
from fred_core.teams.metadata_store import TeamMetadataStore
from sqlalchemy.ext.asyncio import AsyncEngine

from control_plane_backend.agent_instances.store import AgentInstanceStore
from control_plane_backend.config.loader import get_loaded_config_file_path
from control_plane_backend.config.models import (
    Configuration,
    LocalContentStorageConfig,
    MinioContentStorageConfig,
)
from control_plane_backend.evaluations.store import EvaluationStore
from control_plane_backend.prompts.store import PromptStore
from control_plane_backend.scheduler.policies.policy_loader import (
    load_conversation_policy_catalog,
)
from control_plane_backend.scheduler.policies.policy_models import (
    ConversationPolicyCatalog,
)
from control_plane_backend.scheduler.queue_store import PurgeQueueStore
from control_plane_backend.sessions.attachment_store import SessionAttachmentStore
from control_plane_backend.sessions.store import SessionMetadataStore

logger = logging.getLogger(__name__)


class ApplicationContext:
    def __init__(self, configuration: Configuration):
        self.configuration = configuration
        self._temporal_client_provider: TemporalClientProvider | None = None
        self._policy_catalog: ConversationPolicyCatalog | None = None
        self._policy_catalog_path = self._resolve_policy_catalog_path()
        self._pg_async_engine: AsyncEngine | None = None
        self._session_store: BaseSessionStore | None = None
        self._purge_queue_store: PurgeQueueStore | None = None
        self._team_metadata_store: TeamMetadataStore | None = None
        self._content_store: ContentStore | None = None
        self._rebac_engine: RebacEngine | None = None
        self._agent_instance_store: AgentInstanceStore | None = None
        self._session_metadata_store: SessionMetadataStore | None = None
        self._session_attachment_store: SessionAttachmentStore | None = None
        self._prompt_store: PromptStore | None = None
        self._task_service: TaskService | None = None
        self._evaluation_store: EvaluationStore | None = None

    def _resolve_policy_catalog_path(self) -> Path:
        configured = Path(self.configuration.policies.purge_catalog_path)
        if configured.is_absolute():
            return configured

        loaded_config = get_loaded_config_file_path()
        if loaded_config:
            config_dir = Path(loaded_config).resolve().parent
            return (config_dir / configured).resolve()

        return configured.resolve()

    def get_policy_catalog_path(self) -> Path:
        return self._policy_catalog_path

    def get_policy_catalog(self, *, reload: bool = False) -> ConversationPolicyCatalog:
        if self._policy_catalog is None or reload:
            self._policy_catalog = load_conversation_policy_catalog(
                self._policy_catalog_path
            )
            logger.info(
                "Loaded conversation policy catalog from %s",
                self._policy_catalog_path,
            )
        return self._policy_catalog

    def get_scheduler_backend(self) -> SchedulerBackend:
        if not self.configuration.scheduler.enabled:
            return SchedulerBackend.MEMORY
        return resolve_scheduler_backend(self.configuration.scheduler.backend)

    def get_temporal_client_provider(self) -> TemporalClientProvider:
        scheduler_backend = self.get_scheduler_backend()
        if scheduler_backend != SchedulerBackend.TEMPORAL:
            raise ValueError(
                "Temporal client requested but scheduler backend is "
                f"{scheduler_backend}"
            )
        if self._temporal_client_provider is None:
            self._temporal_client_provider = TemporalClientProvider(
                self.configuration.scheduler.temporal
            )
        return self._temporal_client_provider

    def get_pg_async_engine(self) -> AsyncEngine:
        if self._pg_async_engine is None:
            self._pg_async_engine = create_async_engine_from_config(
                self.configuration.storage.postgres
            )
        return self._pg_async_engine

    def get_session_store(self) -> BaseSessionStore:
        if self._session_store is None:
            self._session_store = PostgresSessionStore(
                engine=self.get_pg_async_engine(),
            )
        return self._session_store

    def get_purge_queue_store(self) -> PurgeQueueStore:
        if self._purge_queue_store is None:
            self._purge_queue_store = PurgeQueueStore(
                engine=self.get_pg_async_engine(),
            )
        return self._purge_queue_store

    def get_team_metadata_store(self) -> TeamMetadataStore:
        if self._team_metadata_store is None:
            self._team_metadata_store = TeamMetadataStore(
                engine=self.get_pg_async_engine()
            )
        return self._team_metadata_store

    def get_content_store(self) -> ContentStore:
        if self._content_store is None:
            cfg = self.configuration.storage.content_storage
            if isinstance(cfg, MinioContentStorageConfig):
                self._content_store = MinioContentStore(
                    endpoint=cfg.endpoint,
                    access_key=cfg.access_key,
                    secret_key=cfg.secret_key or "",
                    bucket_name=f"{cfg.bucket_name}-objects",
                    secure=cfg.secure,
                    public_endpoint=cfg.public_endpoint,
                    public_secure=cfg.public_secure,
                )
            elif isinstance(cfg, LocalContentStorageConfig):
                self._content_store = LocalContentStore(root_path=cfg.root_path)
            else:
                raise ValueError(
                    f"Unsupported content storage configuration: {type(cfg)}"
                )
        return self._content_store

    def get_rebac_engine(self) -> RebacEngine:
        if self._rebac_engine is None:
            self._rebac_engine = rebac_factory(self.configuration.security)
        return self._rebac_engine

    def get_agent_instance_store(self) -> AgentInstanceStore:
        if self._agent_instance_store is None:
            self._agent_instance_store = AgentInstanceStore(
                engine=self.get_pg_async_engine()
            )
        return self._agent_instance_store

    def get_session_metadata_store(self) -> SessionMetadataStore:
        if self._session_metadata_store is None:
            self._session_metadata_store = SessionMetadataStore(
                engine=self.get_pg_async_engine()
            )
        return self._session_metadata_store

    def get_session_attachment_store(self) -> SessionAttachmentStore:
        if self._session_attachment_store is None:
            self._session_attachment_store = SessionAttachmentStore(
                engine=self.get_pg_async_engine()
            )
        return self._session_attachment_store

    def get_prompt_store(self) -> PromptStore:
        if self._prompt_store is None:
            self._prompt_store = PromptStore(engine=self.get_pg_async_engine())
        return self._prompt_store

    def get_task_service(self) -> TaskService:
        if self._task_service is None:
            backend = self.get_scheduler_backend()
            temporal_provider = (
                self.get_temporal_client_provider()
                if backend == SchedulerBackend.TEMPORAL
                else None
            )
            self._task_service = TaskService.build(
                engine=self.get_pg_async_engine(),
                backend=backend,
                temporal_client_provider=temporal_provider,
                postgres_dsn=self.configuration.storage.postgres.dsn()
                if backend == SchedulerBackend.TEMPORAL
                else None,
            )
        return self._task_service

    def get_evaluation_store(self) -> EvaluationStore:
        if self._evaluation_store is None:
            self._evaluation_store = EvaluationStore(engine=self.get_pg_async_engine())
        return self._evaluation_store

    async def shutdown(self) -> None:
        if self._rebac_engine is not None:
            try:
                await self._rebac_engine.close()
            except Exception:
                logger.debug("[REBAC] Failed to close ReBAC engine", exc_info=True)
            finally:
                self._rebac_engine = None

        if self._pg_async_engine is not None:
            try:
                await self._pg_async_engine.dispose()
            finally:
                self._pg_async_engine = None
