from __future__ import annotations

import logging
from pathlib import Path

from fred_core import (
    BaseSessionStore,
    M2MAuthConfig,
    M2MTokenProvider,
    PostgresSessionStore,
    RebacEngine,
    rebac_factory,
)
from fred_core.kpi.base_kpi_writer import BaseKPIWriter
from fred_core.kpi.kpi_factory import build_kpi_writer
from fred_core.scheduler import (
    SchedulerBackend,
    TemporalClientProvider,
    resolve_scheduler_backend,
)
from fred_core.sql import create_async_engine_from_config
from fred_core.store import (
    ContentStore,
    GcsContentStore,
    LocalContentStore,
    MinioContentStore,
)
from fred_core.tasks.service import TaskService
from fred_core.teams.metadata_store import TeamMetadataStore
from prometheus_client import start_http_server
from sqlalchemy.ext.asyncio import AsyncEngine

from control_plane_backend.agent_instances.store import AgentInstanceStore
from control_plane_backend.bootstrap.store import PlatformBootstrapStore
from control_plane_backend.capabilities.settings_store import (
    TeamCapabilitySettingsStore,
)
from control_plane_backend.config.loader import get_loaded_config_file_path
from control_plane_backend.config.models import (
    Configuration,
    GcsContentStorageConfig,
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
        self._kpi_writer: BaseKPIWriter | None = None
        self._session_store: BaseSessionStore | None = None
        self._purge_queue_store: PurgeQueueStore | None = None
        self._team_metadata_store: TeamMetadataStore | None = None
        self._platform_bootstrap_store: PlatformBootstrapStore | None = None
        self._content_store: ContentStore | None = None
        self._rebac_engine: RebacEngine | None = None
        self._agent_instance_store: AgentInstanceStore | None = None
        self._team_capability_settings_store: TeamCapabilitySettingsStore | None = None
        self._session_metadata_store: SessionMetadataStore | None = None
        self._session_attachment_store: SessionAttachmentStore | None = None
        self._prompt_store: PromptStore | None = None
        self._task_service: TaskService | None = None
        self._evaluation_store: EvaluationStore | None = None
        self._service_token_provider: M2MTokenProvider | None = None

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

    def get_kpi_writer(self) -> BaseKPIWriter:
        if self._kpi_writer is None:
            self._kpi_writer = build_kpi_writer(
                kpi_config=self.configuration.observability.kpi,
                opensearch_config=self.configuration.storage.opensearch,
                service_name="control-plane",
                log_level=self.configuration.app.log_level,
            )
        return self._kpi_writer

    def get_kpi_store(self):  # -> OpenSearchKPIStore | None
        from fred_core.common.resilient_sink import ResilientSinkStore
        from fred_core.kpi.kpi_writer import KPIWriter
        from fred_core.kpi.opensearch_kpi_store import OpenSearchKPIStore
        from fred_core.kpi.prometheus_kpi_store import PrometheusKPIStore

        writer = self.get_kpi_writer()
        if not isinstance(writer, KPIWriter):
            return None
        store = writer.store
        if isinstance(store, PrometheusKPIStore):
            store = store._delegate
        # ResilientSinkStore (#2009) wraps the real store for fail-open writes —
        # unwrap it too, or every read-side KPI-preset query 503s even though
        # the write path underneath is a perfectly healthy OpenSearchKPIStore.
        if isinstance(store, ResilientSinkStore):
            store = store.wrapped
        return store if isinstance(store, OpenSearchKPIStore) else None

    def start_metrics_exporter(self) -> None:
        """Start the Prometheus scrape endpoint when configured."""
        prom_cfg = self.configuration.observability.kpi.prometheus
        if not prom_cfg.enabled:
            return
        start_http_server(prom_cfg.port, addr=prom_cfg.address)
        logger.info(
            "[control-plane] Prometheus metrics exporter ready at %s:%s",
            prom_cfg.address,
            prom_cfg.port,
        )

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

    def get_platform_bootstrap_store(self) -> PlatformBootstrapStore:
        if self._platform_bootstrap_store is None:
            self._platform_bootstrap_store = PlatformBootstrapStore(
                engine=self.get_pg_async_engine()
            )
        return self._platform_bootstrap_store

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
            elif isinstance(cfg, GcsContentStorageConfig):
                # Fail fast at startup: banner/logo images are served straight to the
                # browser via get_presigned_url, which needs a signing SA to mint V4
                # signed URLs via IAM signBlob (no per-feature flag to detect that
                # usage later, so a missing email must stop the boot here rather than
                # surfacing as an opaque runtime error on first team-banner render).
                if not cfg.signing_service_account_email:
                    raise ValueError(
                        "content_storage.type=gcs requires 'signing_service_account_email' "
                        "to sign V4 signed URLs for team banner/logo images (IAM signBlob "
                        "under Workload Identity, no JSON key). Set it to the signing "
                        "service account that holds storage.objects.get on the objects "
                        "bucket and on which the Workload Identity service account has "
                        "iam.serviceAccounts.signBlob."
                    )
                self._content_store = GcsContentStore(
                    bucket_name=f"{cfg.bucket_name}-objects",
                    project_id=cfg.project_id,
                    signing_service_account_email=cfg.signing_service_account_email,
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

    def get_service_token_provider(self) -> M2MTokenProvider:
        """Client-credentials token minter for the control-plane service account.

        CTRLP-12 C2: the server-initiated erase path (lifecycle erase-at-expiry)
        has no user bearer, so it authenticates as the platform service principal
        using the **existing** ``control-plane`` Keycloak service account
        (``security.m2m``). Reuses the shared ``M2MTokenProvider`` (cached,
        refreshing client-credentials grant) — no bespoke token code. The SA's
        token carries a ``sub`` (so the runtime/KF accept it) and, once granted
        ``can_manage_platform``, the delete endpoints' C1 admin branch waives
        ownership.
        """
        if self._service_token_provider is None:
            m2m = self.configuration.security.m2m
            self._service_token_provider = M2MTokenProvider(
                M2MAuthConfig(
                    keycloak_realm_url=str(m2m.realm_url).rstrip("/"),
                    client_id=m2m.client_id,
                    secret_env=m2m.secret_env_var,
                )
            )
        return self._service_token_provider

    async def get_service_bearer(self) -> str:
        """Mint (or reuse a cached) service token as an ``Authorization`` value.

        Returns ``"Bearer <token>"`` for the lifecycle erase calls. Fails closed:
        ``M2MTokenProvider.get_token`` raises when the client secret is missing or
        the token endpoint refuses — the lifecycle treats that as a retryable
        error and leaves the queue entry un-done (CTRLP-12 C2/E1).
        """
        token = await self.get_service_token_provider().get_token()
        return f"Bearer {token}"

    def get_agent_instance_store(self) -> AgentInstanceStore:
        if self._agent_instance_store is None:
            self._agent_instance_store = AgentInstanceStore(
                engine=self.get_pg_async_engine()
            )
        return self._agent_instance_store

    def get_team_capability_settings_store(self) -> TeamCapabilitySettingsStore:
        if self._team_capability_settings_store is None:
            self._team_capability_settings_store = TeamCapabilitySettingsStore(
                engine=self.get_pg_async_engine()
            )
        return self._team_capability_settings_store

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
