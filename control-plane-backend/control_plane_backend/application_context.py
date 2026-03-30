from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

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
from sqlalchemy.ext.asyncio import AsyncEngine

from control_plane_backend.common.config_loader import get_loaded_config_file_path
from control_plane_backend.common.structures import (
    Configuration,
    LocalContentStorageConfig,
    MinioContentStorageConfig,
)
from control_plane_backend.purge_queue_store import PurgeQueueStore
from control_plane_backend.scheduler.policies.policy_loader import (
    load_conversation_policy_catalog,
)
from control_plane_backend.scheduler.policies.policy_models import (
    ConversationPolicyCatalog,
)
from control_plane_backend.team_metadata_store import TeamMetadataStore

logger = logging.getLogger(__name__)


class ApplicationContext:
    _instance: Optional["ApplicationContext"] = None

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
        ApplicationContext._instance = self

    @classmethod
    def get_instance(cls) -> "ApplicationContext":
        if cls._instance is None:
            raise RuntimeError("ApplicationContext is not initialized yet.")
        return cls._instance

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
                table_name=self.configuration.storage.purge_queue_table,
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


def get_app_context() -> ApplicationContext:
    return ApplicationContext.get_instance()
