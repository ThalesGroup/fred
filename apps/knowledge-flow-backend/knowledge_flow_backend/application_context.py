# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
import logging
import os
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional
from uuid import UUID

import httpx
from fred_core import split_realm_url
from fred_core.common import ModelConfiguration, OpenSearchIndexConfig
from fred_core.kpi import BaseKPIWriter, build_kpi_writer
from fred_core.model import http_clients
from fred_core.security.backend_to_backend_auth import M2MAuthConfig, M2MBearerAuth, M2MTokenProvider
from fred_core.sql import classify_connection_failures, create_async_engine_from_config
from fred_knowledge.artifacts.reader import ArtifactReader
from fred_knowledge.models import DocumentModels
from fred_knowledge.text.base_text_splitter import BaseTextSplitter
from fred_knowledge.text.semantic_splitter import SemanticSplitter
from fred_knowledge.vector.base_vector_store import BaseVectorStore
from fred_knowledge.vector.factory import build_vector_store
from fred_pod.common.structures import OPENSEARCH_PASSWORD_ENV, POSTGRES_PASSWORD_ENV
from fred_pod.security.oidc_endpoints import resolve_endpoints
from fred_sdk.contracts.weaver import InferenceAdmission
from opensearchpy import OpenSearch, RequestsHttpConnection
from sqlalchemy.ext.asyncio import AsyncEngine

from knowledge_flow_backend.common.structures import Configuration, PgVectorStorageConfig, TabularStoreConfig

if TYPE_CHECKING:
    from sentence_transformers import CrossEncoder
logger = logging.getLogger(__name__)


def get_configuration() -> Configuration:
    """
    Retrieves the global application configuration.

    Returns:
        Configuration: The singleton application configuration.
    """
    return get_app_context().configuration


def get_kpi_writer() -> BaseKPIWriter:
    """
    Retrieves the global KPI writer instance.

    Returns:
        KPIWriter: The singleton KPI writer instance.
    """
    return get_app_context().get_kpi_writer()


def get_app_context() -> "ApplicationContext":
    """
    Retrieves the global application context instance.

    Returns:
        ApplicationContext: The singleton application context.

    Raises:
        RuntimeError: If the context has not been initialized yet.
    """
    if ApplicationContext._instance is None:
        raise RuntimeError("ApplicationContext is not yet initialized")
    return ApplicationContext._instance


class ApplicationContext:
    _instance: Optional["ApplicationContext"] = None

    def __init__(self, configuration: Configuration):
        if ApplicationContext._instance is not None:
            return
        self.configuration = configuration
        self._published_artifact_reader: ArtifactReader | None = None
        self._document_models = DocumentModels(configuration.inference_credentials)
        self._corpus_lock = threading.Lock()
        self._corpus_stores: dict[tuple, BaseVectorStore] = {}
        self._kpi_writer: BaseKPIWriter | None = None
        self._control_plane_client: httpx.AsyncClient | None = None
        self._pg_async_engine: AsyncEngine | None = None
        self._opensearch_client: OpenSearch | None = None
        ApplicationContext._instance = self
        self._log_config_summary()

    def get_text_splitter(self) -> BaseTextSplitter:
        return SemanticSplitter(**self.configuration.text_splitter.model_dump())

    def _log_sensitive(self, name: str, value: Optional[str]):
        logger.info("%s configured: %s", name, bool(value))

    def _log_config_summary(self):
        sec = self.configuration.security.user

        logger.info("  🔒 security (Knowledge → Knowledge/Third Party):")
        logger.info("     • enabled: %s", sec.enabled)
        logger.info("     • client_id: %s", sec.client_id or "<unset>")
        logger.info("     • %s: %s", "issuer" if sec.provider == "oidc" else "keycloak_url", sec.realm_url or "<unset>")

        if sec.enabled:
            if sec.provider == "keycloak":
                try:
                    base, realm = split_realm_url(str(sec.realm_url))
                    logger.info("     • realm: %s  (base=%s)", realm, base)
                except Exception as e:
                    logger.error("     ❌ keycloak_url invalid (expected …/realms/<realm>): %s", e)
                    raise ValueError("Invalid Keycloak URL") from e
        logger.info("  🧠 models: admitted per organization by the Control Plane; %d credential binding(s)", len(self.configuration.inference_credentials))

        vector_type = self.configuration.storage.vector_store
        logger.info(f"  📚 Vector store backend: {vector_type}")
        try:
            store = self.configuration.storage.vector_store

            if isinstance(store, OpenSearchIndexConfig):
                s = self.configuration.storage.opensearch
                if not s:
                    logger.error("     ❌ Missing OpenSearch configuration (required for OpenSearch-backed vector store)")
                    raise RuntimeError("OpenSearch configuration is required for OpenSearch vector store")
                _require_env(OPENSEARCH_PASSWORD_ENV)
                logger.info(f"     ↳ Host: {s.host}")
                logger.info(f"     ↳ Vector Index: {store.index}")
                logger.info(f"     ↳ Secure (TLS): {s.secure}")
                logger.info(f"     ↳ Verify Certs: {s.verify_certs}")
                logger.info(f"     ↳ Username: {s.username}")
                self._log_sensitive(OPENSEARCH_PASSWORD_ENV, os.getenv(OPENSEARCH_PASSWORD_ENV))
            elif isinstance(store, PgVectorStorageConfig):
                pg = self.configuration.storage.postgres
                _require_env(POSTGRES_PASSWORD_ENV)
                logger.info("     ↳ Backend: pgvector")
                logger.info("     ↳ Host: %s  Port: %s  DB: %s", pg.host, pg.port, pg.database)
                logger.info("     ↳ Collection: %s", store.collection_name)
                logger.info("     ↳ Username: %s", pg.username)
                self._log_sensitive(POSTGRES_PASSWORD_ENV, os.getenv(POSTGRES_PASSWORD_ENV))
        except Exception:
            logger.warning("⚠️ Failed to load vector store settings — some variables may be missing or misconfigured.")

        try:
            tabular_store: TabularStoreConfig = self.configuration.storage.tabular_store
            logger.info("  📊 Tabular runtime:")
            logger.info(
                "     • prefix=%s  format=%s  compression=%s",
                tabular_store.artifacts_prefix,
                tabular_store.format,
                tabular_store.compression,
            )
            logger.info(
                "     • engine=%s  access=%s  default_max_rows=%s  max_rows=%s  internal_presigned_ttl_seconds=%s",
                tabular_store.query.engine,
                tabular_store.query.access_mode,
                tabular_store.query.default_max_rows,
                tabular_store.query.max_rows,
                tabular_store.query.internal_presigned_ttl_seconds,
            )
        except Exception:
            logger.warning("  ⚠️ Failed to read tabular runtime section.")

    @classmethod
    def get_instance(cls) -> "ApplicationContext":
        """
        Get the singleton instance of ApplicationContext. It provides access to the
        configuration and API resources.
        Raises:
            RuntimeError: If the ApplicationContext is not initialized.
        """
        if cls._instance is None:
            raise RuntimeError("ApplicationContext is not initialized yet.")
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """Reset the singleton instance (used in tests)."""
        cls._instance = None

    def get_config(self) -> Configuration:
        """
        Get the application configuration. This corresponds to the initial YAML file
        loaded at startup.
        """
        return self.configuration

    def get_published_artifact_reader(self) -> ArtifactReader:
        if self._published_artifact_reader is None:
            config = self.configuration.published_artifacts
            if config is None:
                raise RuntimeError("published_artifacts is not configured")
            self._published_artifact_reader = ArtifactReader(config)
        return self._published_artifact_reader

    def get_pg_async_engine(self):
        """
        Lazily create and cache a single async Postgres Engine for all the postgres async stores.
        """
        if self._pg_async_engine is None:
            self._pg_async_engine = self._init_pg_async_engine()
        return self._pg_async_engine

    def _init_pg_async_engine(self):
        pg_cfg = self.configuration.storage.postgres
        pg_async_engine = create_async_engine_from_config(pg_cfg)
        classify_connection_failures(pg_async_engine)

        logger.info("Shared Postgres async initialized.")
        return pg_async_engine

    def get_document_models(self) -> DocumentModels:
        """Builds the Control Plane's admitted models against this workload's bindings."""
        return self._document_models

    def get_crossencoder_model(self) -> "CrossEncoder":
        """
        Retrieve the cross-encoder model based on the application configuration.
        If no cross-encoder model is configured, a default model is used.
        If the model is configured for offline use, it will be loaded from a local path.
        Otherwise, it will be loaded from the Hugging Face model hub.

        Returns:
            CrossEncoder: An instance of the cross-encoder model.
        Raises:
            ValueError: If the model name is required but not provided in offline mode,
                        or if the model configuration is missing.
        """
        from sentence_transformers import CrossEncoder

        # A default model is loaded if none is specified in the configuration.
        if not self.configuration.crossencoder_model:
            self.configuration.crossencoder_model = ModelConfiguration(provider=None, name="cross-encoder/ms-marco-MiniLM-L-12-v2")
            try:
                self.configuration.crossencoder_model = ModelConfiguration(provider=None, name="cross-encoder/ms-marco-MiniLM-L-12-v2")
                return CrossEncoder(model_name_or_path="cross-encoder/ms-marco-MiniLM-L-12-v2", cache_folder=None)
            except Exception as e:
                logging.error(f"The configuration is missing : Error: {e}")
                logging.error("Loading a default model : cross-encoder/ms-marco-MiniLM-L-12-v2")
                default_cache = str(Path.home() / ".cache" / "huggingface")
                return CrossEncoder(
                    model_name_or_path="cross-encoder/ms-marco-MiniLM-L-12-v2",
                    cache_folder=default_cache,
                    local_files_only=True,
                )

        model_config = self.configuration.crossencoder_model
        settings: Dict[str, Any] = model_config.settings or {}

        # Offline mode
        if not settings.get("online", True):
            if not model_config.name:
                raise ValueError("The name of the cross-encoder model is required for offline mode.")
            configured_local_path = settings.get("local_path")
            if not configured_local_path:
                raise ValueError("A path to the local cross-encoder model is required for offline mode.")

            expanded = os.path.expandvars(str(configured_local_path))
            resolved_local_path = str(Path(expanded).expanduser().resolve(strict=False))

            logging.info("Offline mode enabled.")
            logging.info("Using configured local_path: %s", resolved_local_path)
            try:
                return CrossEncoder(
                    model_name_or_path=model_config.name,
                    cache_folder=resolved_local_path,
                    local_files_only=True,
                )
            except Exception as e:
                raise ValueError(f"[CROSSENCODER][OFFLINE] Could not load model '{model_config.name}' from local_path '{resolved_local_path}': {e}") from e

        if not model_config.name:
            raise ValueError("The name of the cross-encoder model is required.")

        return CrossEncoder(model_name_or_path=model_config.name, cache_folder=None)

    def get_corpus_store(self, organization_id: UUID, embedding: InferenceAdmission) -> BaseVectorStore:
        """One organization's corpus, searched with its locked embedding model; read-only."""
        key = (organization_id, DocumentModels.identity(embedding))
        with self._corpus_lock:
            if key not in self._corpus_stores:
                self._corpus_stores[key] = build_vector_store(
                    self._document_models.embeddings(embedding),
                    self.configuration.storage.vector_store,
                    organization_id=organization_id,
                    embedding_model_name=embedding.selection.key.upstream_model_id,
                    opensearch_config=self.configuration.storage.opensearch,
                    postgres_config=self.configuration.storage.postgres,
                    kpi=self.get_kpi_writer(),
                    splitter=self.get_text_splitter(),
                    read_only=True,
                )
            return self._corpus_stores[key]

    def get_opensearch_client(self) -> OpenSearch:
        if self._opensearch_client is not None:
            return self._opensearch_client

        opensearch_config = get_configuration().storage.opensearch
        if not opensearch_config:
            raise ValueError("Missing OpenSearch configuration")

        self._opensearch_client = OpenSearch(
            opensearch_config.host,
            http_auth=(opensearch_config.username, opensearch_config.password),
            use_ssl=opensearch_config.secure,
            verify_certs=opensearch_config.verify_certs,
            connection_class=RequestsHttpConnection,
        )
        return self._opensearch_client

    def get_kpi_writer(self) -> BaseKPIWriter:
        if self._kpi_writer is not None:
            return self._kpi_writer

        self._kpi_writer = build_kpi_writer(
            kpi_config=self.configuration.observability.kpi,
            opensearch_config=self.configuration.storage.opensearch,
            service_name="knowledge-flow",
            log_level=self.configuration.app.log_level,
        )
        return self._kpi_writer

    def open_authorization_client(self) -> None:
        security = self.configuration.security
        m2m = security.m2m
        if not m2m.enabled or not security.delegation.act_for_people or not self.configuration.control_plane_url:
            raise ValueError("Knowledge Flow API requires Control Plane URL, workload credentials and security.delegation.act_for_people")
        endpoint = resolve_endpoints(provider=m2m.provider, realm_url=str(m2m.realm_url).rstrip("/"), token_url=str(m2m.token_url) if m2m.token_url else None)
        provider = M2MTokenProvider(
            M2MAuthConfig(keycloak_realm_url=str(m2m.realm_url).rstrip("/"), client_id=m2m.client_id, scope=m2m.scope, secret_env=m2m.secret_env_var, token_url_override=endpoint.token_endpoint)
        )
        self._control_plane_client = httpx.AsyncClient(auth=M2MBearerAuth(provider), timeout=10.0, follow_redirects=False)

    def get_authorization_client(self) -> httpx.AsyncClient:
        if self._control_plane_client is None:
            raise RuntimeError("Control Plane client is opened at API startup")
        return self._control_plane_client

    async def shutdown(self) -> None:
        """
        Best-effort cleanup of shared resources.
        """
        # HTTP clients
        try:
            await http_clients.async_shutdown_shared_clients()
        except Exception:
            logger.debug("Failed to shutdown shared clients", exc_info=True)

        if self._control_plane_client is not None:
            await self._control_plane_client.aclose()

        # Async PG engine
        if self._pg_async_engine is not None:
            try:
                await self._pg_async_engine.dispose()
            finally:
                self._pg_async_engine = None

        # OpenSearch client
        if self._opensearch_client is not None:
            try:
                self._opensearch_client.close()
            except Exception:
                logger.debug("Error closing OpenSearch client", exc_info=True)
            finally:
                self._opensearch_client = None


def _mask(value: Optional[str]) -> str:
    """Never reveal any character of a secret — a partial preview is still a leak
    (a short secret's `left`/`right` window can cover most of its length)."""
    return "<empty>" if not value else "<redacted>"


def _require_env(var: str) -> None:
    """Log presence of a required env var or raise loudly if missing."""
    val = os.getenv(var, "")
    if val:
        logger.info("     • %s: present (%s)", var, _mask(val))
        return
    logger.error("     ❌ %s is not set", var)
    raise ValueError(f"Missing required environment variable: {var}")
