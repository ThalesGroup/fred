# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import asyncio
import atexit
import logging
import threading
from typing import Any, Dict, Optional, Tuple

import httpx
from fred_core.model.http_clients import TransportTuning, compute_transport_tuning

logger = logging.getLogger(__name__)


_LOCK = threading.RLock()
_TUNING: Optional[TransportTuning] = None
_ASYNC_CLIENT: Optional[httpx.AsyncClient] = None


def _build_settings(
    timeout_cfg: Dict[str, Any], limits_cfg: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    settings: Dict[str, Any] = {
        "timeout": timeout_cfg,
    }
    if limits_cfg is not None:
        settings["http_client_limits"] = limits_cfg
    return settings


def get_shared_kf_async_client(
    *, timeout_cfg: Dict[str, Any], limits_cfg: Optional[Dict[str, Any]] = None
) -> Tuple[TransportTuning, httpx.AsyncClient]:
    """Return a process-wide async client + its tuning for KF traffic."""

    settings = _build_settings(timeout_cfg, limits_cfg)
    requested = compute_transport_tuning(settings)

    global _TUNING, _ASYNC_CLIENT
    with _LOCK:
        if _ASYNC_CLIENT is None:
            _TUNING = requested
            _ASYNC_CLIENT = httpx.AsyncClient(
                limits=requested.limits,
                timeout=requested.timeout,
            )
            atexit.register(close_shared_kf_async_client)
            logger.info(
                "[KF][NET] Shared async client init limits(max=%s keepalive=%s exp=%ss) "
                "timeout(connect=%ss read=%ss write=%ss pool=%ss)",
                requested.limits.max_connections,
                requested.limits.max_keepalive_connections,
                requested.limits.keepalive_expiry,
                requested.timeout.connect,
                requested.timeout.read,
                requested.timeout.write,
                requested.timeout.pool,
            )
        else:
            if _TUNING and requested != _TUNING:
                logger.warning(
                    "[KF][NET] Shared client already initialized; ignoring new tuning requested=%s active=%s",
                    requested,
                    _TUNING,
                )

        assert _ASYNC_CLIENT is not None
        assert _TUNING is not None
        return _TUNING, _ASYNC_CLIENT


def close_shared_kf_async_client() -> None:
    global _ASYNC_CLIENT
    with _LOCK:
        client = _ASYNC_CLIENT
        _ASYNC_CLIENT = None
    if client is None:
        return
    try:
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = None

        async def _close():
            try:
                await client.aclose()
            except Exception:
                logger.debug(
                    "[KF][NET] Suppressed error during async client close",
                    exc_info=True,
                )

        if loop is not None and loop.is_running() and not loop.is_closed():
            loop.create_task(_close())
        else:
            try:
                asyncio.run(_close())
            except RuntimeError:
                # If the loop is already closed or shutting down, skip close silently.
                logger.debug("[KF][NET] Event loop closed during close; skipping")
    except Exception:
        logger.exception("[KF][NET] Error closing shared async client")


async def async_close_shared_kf_async_client() -> None:
    global _ASYNC_CLIENT
    with _LOCK:
        client = _ASYNC_CLIENT
        _ASYNC_CLIENT = None
    if client is None:
        return
    try:
        await client.aclose()
    except Exception:
        logger.exception("[KF][NET] Error closing shared async client")
