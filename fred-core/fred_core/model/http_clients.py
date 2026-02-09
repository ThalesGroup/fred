# fred_core/model/http_clients.py
#
# Copyright Thales 2025
# Licensed under the Apache License, Version 2.0

from __future__ import annotations

import asyncio
import atexit
import logging
import threading
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import httpx

from fred_core.common.structures import ModelConfiguration

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TransportTuning:
    """
    Pure, deterministic representation of transport tuning derived from YAML.
    Safe to log (no secrets). Stable across providers.
    """

    limits: httpx.Limits
    timeout: httpx.Timeout


# ---------------------------------------------------------------------------
# Defaults (single source of truth for transport)
# ---------------------------------------------------------------------------

_DEFAULT_LIMITS = {
    "max_connections": 500,
    "max_keepalive_connections": 50,  # keep-alive ON by default (production-friendly)
    "keepalive_expiry_seconds": 10.0,
}

_DEFAULT_TIMEOUT = {
    # Under load, "pool" timeout prevents infinite wait for a free connection.
    "connect": 10.0,
    "read": 120.0,
    "write": 30.0,
    "pool": 5.0,
}


# ---------------------------------------------------------------------------
# Global singleton state (thread-safe)
# ---------------------------------------------------------------------------

_LOCK = threading.RLock()
_SHARED_TUNING: Optional[TransportTuning] = None
_SYNC_CLIENT: Optional[httpx.Client] = None
_ASYNC_CLIENT: Optional[httpx.AsyncClient] = None


# ---------------------------------------------------------------------------
# Parsing helpers (pure)
# ---------------------------------------------------------------------------


def _as_nonneg_int(v: Any, name: str) -> int:
    try:
        iv = int(v)
    except Exception as e:
        raise ValueError(f"{name} must be an int") from e
    if iv < 0:
        raise ValueError(f"{name} must be >= 0")
    return iv


def _as_nonneg_float(v: Any, name: str) -> float:
    try:
        fv = float(v)
    except Exception as e:
        raise ValueError(f"{name} must be a float") from e
    if fv < 0:
        raise ValueError(f"{name} must be >= 0")
    return fv


def _parse_limits(settings: Dict[str, Any]) -> httpx.Limits:
    cfg = settings.get("http_client_limits")
    if cfg is None:
        cfg = {}
    if not isinstance(cfg, dict):
        logger.warning(
            "[NET] http_client_limits ignored (expected dict, got %s).",
            type(cfg).__name__,
        )
        cfg = {}

    merged = {**_DEFAULT_LIMITS, **cfg}

    return httpx.Limits(
        max_connections=_as_nonneg_int(
            merged["max_connections"], "http_client_limits.max_connections"
        ),
        max_keepalive_connections=_as_nonneg_int(
            merged["max_keepalive_connections"],
            "http_client_limits.max_keepalive_connections",
        ),
        keepalive_expiry=_as_nonneg_float(
            merged["keepalive_expiry_seconds"],
            "http_client_limits.keepalive_expiry_seconds",
        ),
    )


def _parse_timeout(settings: Dict[str, Any]) -> httpx.Timeout:
    # Transport timeouts should come from "timeout".
    # For backward compatibility, if only request_timeout is provided, reuse it for transport.
    raw_timeout = settings.get("timeout", None)
    raw_request = settings.get("request_timeout", None)

    if raw_timeout is None and raw_request is not None:
        logger.warning(
            "[NET] timeout not set; using request_timeout=%s for transport. Set timeout to avoid this fallback.",
            raw_request,
        )
        raw = raw_request
    else:
        raw = raw_timeout

    # Numeric: apply to all phases.
    if isinstance(raw, (int, float)):
        return httpx.Timeout(float(raw))

    # Dict: connect/read/write/pool (recommended).
    if isinstance(raw, dict):
        merged = {**_DEFAULT_TIMEOUT, **raw}
        return httpx.Timeout(
            connect=_as_nonneg_float(merged["connect"], "timeout.connect"),
            read=_as_nonneg_float(merged["read"], "timeout.read"),
            write=_as_nonneg_float(merged["write"], "timeout.write"),
            pool=_as_nonneg_float(merged["pool"], "timeout.pool"),
        )

    # Missing or unsupported type -> defaults
    if raw is not None:
        logger.warning(
            "[NET] timeout ignored (expected number or dict, got %s).",
            type(raw).__name__,
        )

    return httpx.Timeout(
        connect=_DEFAULT_TIMEOUT["connect"],
        read=_DEFAULT_TIMEOUT["read"],
        write=_DEFAULT_TIMEOUT["write"],
        pool=_DEFAULT_TIMEOUT["pool"],
    )


def compute_transport_tuning(settings: Dict[str, Any]) -> TransportTuning:
    """
    Pure function: returns the tuning that SHOULD be applied for a given settings dict.
    Does not mutate settings and does not allocate clients.
    """
    return TransportTuning(
        limits=_parse_limits(settings),
        timeout=_parse_timeout(settings),
    )


def strip_transport_settings(settings: Dict[str, Any]) -> None:
    """
    Mutating helper: removes transport-only keys so they do NOT get forwarded
    into LangChain wrapper kwargs (which may not accept dict timeouts etc.).
    """
    settings.pop("http_client_limits", None)
    settings.pop("timeout", None)
    # keep request_timeout so it can be forwarded to the LLM wrapper as a per-request timeout


# ---------------------------------------------------------------------------
# Singleton allocation + shutdown
# ---------------------------------------------------------------------------


def get_shared_stack(
    cfg: ModelConfiguration,
    *,
    settings: Optional[Dict[str, Any]] = None,
) -> Tuple[TransportTuning, httpx.Client, httpx.AsyncClient]:
    """
    Returns (tuning, sync_client, async_client).

    Industrial constraints:
    - single connection pool for the process (predictable, measurable)
    - explicit, bounded timeouts including pool timeout (no silent hangs)
    - safe init in multi-threaded startup
    - deterministic cleanup at process exit

    IMPORTANT:
    - The first call initializes the singleton using the provided settings (or cfg.settings).
    - Subsequent calls return the existing stack; if settings differ, we log and ignore.
    """
    global _SHARED_TUNING, _SYNC_CLIENT, _ASYNC_CLIENT

    # We never want to mutate cfg.settings (could be reused elsewhere)
    effective_settings = dict(
        settings if settings is not None else (cfg.settings or {})
    )
    requested = compute_transport_tuning(effective_settings)

    with _LOCK:
        if _SHARED_TUNING is None:
            _SHARED_TUNING = requested
            _SYNC_CLIENT = httpx.Client(
                limits=_SHARED_TUNING.limits,
                timeout=_SHARED_TUNING.timeout,
            )
            _ASYNC_CLIENT = httpx.AsyncClient(
                limits=_SHARED_TUNING.limits,
                timeout=_SHARED_TUNING.timeout,
            )

            atexit.register(shutdown_shared_clients)

            logger.info(
                "[NET] Shared HTTPX stack init provider=%s "
                "limits(max_conn=%s keepalive=%s keepalive_expiry=%ss) "
                "timeout(connect=%ss read=%ss write=%ss pool=%ss)",
                cfg.provider,
                _SHARED_TUNING.limits.max_connections,
                _SHARED_TUNING.limits.max_keepalive_connections,
                _SHARED_TUNING.limits.keepalive_expiry,
                _SHARED_TUNING.timeout.connect,
                _SHARED_TUNING.timeout.read,
                _SHARED_TUNING.timeout.write,
                _SHARED_TUNING.timeout.pool,
            )
            logger.warning(
                "[NET][TUNING] provider=%s applied_limits={max=%s keepalive=%s exp=%ss} "
                "applied_timeout={connect=%ss read=%ss write=%ss pool=%ss} "
                "from_settings=%s",
                cfg.provider,
                _SHARED_TUNING.limits.max_connections,
                _SHARED_TUNING.limits.max_keepalive_connections,
                _SHARED_TUNING.limits.keepalive_expiry,
                _SHARED_TUNING.timeout.connect,
                _SHARED_TUNING.timeout.read,
                _SHARED_TUNING.timeout.write,
                _SHARED_TUNING.timeout.pool,
                effective_settings,
            )
        else:
            if requested != _SHARED_TUNING:
                logger.warning(
                    "[NET] Shared HTTPX stack already initialized; ignoring new tuning. "
                    "provider=%s requested=%s active=%s",
                    cfg.provider,
                    requested,
                    _SHARED_TUNING,
                )
            else:
                logger.warning(
                    "[NET][TUNING] provider=%s reusing shared stack "
                    "limits(max=%s keepalive=%s exp=%ss) "
                    "timeout(connect=%ss read=%ss write=%ss pool=%ss)",
                    cfg.provider,
                    _SHARED_TUNING.limits.max_connections,
                    _SHARED_TUNING.limits.max_keepalive_connections,
                    _SHARED_TUNING.limits.keepalive_expiry,
                    _SHARED_TUNING.timeout.connect,
                    _SHARED_TUNING.timeout.read,
                    _SHARED_TUNING.timeout.write,
                    _SHARED_TUNING.timeout.pool,
                )

        assert _SHARED_TUNING is not None
        assert _SYNC_CLIENT is not None
        assert _ASYNC_CLIENT is not None
        return _SHARED_TUNING, _SYNC_CLIENT, _ASYNC_CLIENT


def shutdown_shared_clients() -> None:
    """
    Best-effort shutdown. Never raises.
    """
    global _SYNC_CLIENT, _ASYNC_CLIENT

    with _LOCK:
        sync_client = _SYNC_CLIENT
        async_client = _ASYNC_CLIENT
        _SYNC_CLIENT = None
        _ASYNC_CLIENT = None

    if sync_client is not None:
        try:
            sync_client.close()
            logger.info("[NET] Sync HTTPX client closed.")
        except Exception:
            logger.exception("[NET] Error closing Sync HTTPX client.")

    if async_client is not None:

        async def _close() -> None:
            await async_client.aclose()

        try:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = None

            if loop is not None and loop.is_running():
                # Best-effort scheduling; avoids blocking shutdown in async servers.
                loop.create_task(_close())
            else:
                asyncio.run(_close())

            logger.info("[NET] Async HTTPX client closed.")
        except Exception:
            logger.exception("[NET] Error closing Async HTTPX client.")


async def async_shutdown_shared_clients() -> None:
    """
    Async variant that awaits async client closure when a running loop is available.
    """
    global _SYNC_CLIENT, _ASYNC_CLIENT

    with _LOCK:
        sync_client = _SYNC_CLIENT
        async_client = _ASYNC_CLIENT
        _SYNC_CLIENT = None
        _ASYNC_CLIENT = None

    if sync_client is not None:
        try:
            sync_client.close()
            logger.info("[NET] Sync HTTPX client closed.")
        except Exception:
            logger.exception("[NET] Error closing Sync HTTPX client.")

    if async_client is not None:
        try:
            await async_client.aclose()
            logger.info("[NET] Async HTTPX client closed.")
        except Exception:
            logger.exception("[NET] Error closing Async HTTPX client.")
