from __future__ import annotations

import os
from contextlib import AsyncExitStack, asynccontextmanager, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, HTTPException, Request, Response
from httpx import ASGITransport, AsyncClient, Headers

from app_backend.common.config_loader import (
    get_loaded_config_file_path,
    load_configuration,
)
from app_backend.common.structures import Configuration, EmbeddedServiceConfig

BackendFactory = Callable[[], FastAPI]

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
    "content-length",
}

FORWARDED_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]


@dataclass(frozen=True)
class BackendSpec:
    name: str
    path_prefix: str
    config_file: Path
    factory: BackendFactory


@dataclass
class BackendRuntime:
    spec: BackendSpec
    app: FastAPI
    client: AsyncClient | None = None


@contextmanager
def _backend_config_scope(config_file: Path):
    previous_config_file = os.environ.get("CONFIG_FILE")
    os.environ["CONFIG_FILE"] = str(config_file)
    try:
        yield
    finally:
        if previous_config_file is None:
            os.environ.pop("CONFIG_FILE", None)
        else:
            os.environ["CONFIG_FILE"] = previous_config_file


def _load_backend_factories() -> dict[str, BackendFactory]:
    from agentic_backend.main import create_app as create_agentic_app
    from control_plane_backend.main import create_app as create_control_plane_app
    from knowledge_flow_backend.main import create_app as create_knowledge_flow_app

    return {
        "control_plane": create_control_plane_app,
        "agentic": create_agentic_app,
        "knowledge_flow": create_knowledge_flow_app,
    }


def _resolve_config_path(raw_path: str, config_dir: Path) -> Path:
    candidate = Path(raw_path).expanduser()
    if candidate.is_absolute():
        return candidate
    return (config_dir / candidate).resolve()


def _build_backend_specs(
    configuration: Configuration,
    config_dir: Path,
    factories: dict[str, BackendFactory],
) -> list[BackendSpec]:
    service_entries: list[tuple[str, str, EmbeddedServiceConfig]] = [
        ("control-plane", "control_plane", configuration.services.control_plane),
        ("agentic", "agentic", configuration.services.agentic),
        ("knowledge-flow", "knowledge_flow", configuration.services.knowledge_flow),
    ]

    specs: list[BackendSpec] = []
    for display_name, key, service in service_entries:
        if not service.enabled:
            continue
        factory = factories.get(key)
        if factory is None:
            raise RuntimeError(f"Missing backend factory for service '{key}'")
        specs.append(
            BackendSpec(
                name=display_name,
                path_prefix=service.path_prefix,
                config_file=_resolve_config_path(service.config_file, config_dir),
                factory=factory,
            )
        )
    return specs


def _path_matches_prefix(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(f"{prefix}/")


def _find_backend(path: str, backends: list[BackendRuntime]) -> BackendRuntime | None:
    for backend in backends:
        if _path_matches_prefix(path, backend.spec.path_prefix):
            return backend
    return None


def _copy_proxy_headers(target: Response, source_headers: Headers) -> None:
    for name, value in source_headers.multi_items():
        if name.lower() in HOP_BY_HOP_HEADERS:
            continue
        target.headers.append(name, value)


async def _proxy_request(request: Request, backend: BackendRuntime) -> Response:
    if backend.client is None:
        raise RuntimeError(
            f"Proxy client is not initialized for backend {backend.spec.name}"
        )

    request_path = request.url.path
    if request.url.query:
        request_path = f"{request_path}?{request.url.query}"

    headers = dict(request.headers)
    headers.pop("host", None)

    upstream = await backend.client.request(
        request.method,
        request_path,
        headers=headers,
        content=await request.body(),
    )

    response = Response(
        content=upstream.content,
        status_code=upstream.status_code,
    )
    _copy_proxy_headers(response, upstream.headers)
    return response


def create_app() -> FastAPI:
    configuration = load_configuration()
    loaded_config_file = get_loaded_config_file_path()
    if loaded_config_file:
        config_dir = Path(loaded_config_file).resolve().parent
    else:
        config_dir = Path.cwd()

    backends: list[BackendRuntime] = []
    specs = _build_backend_specs(
        configuration,
        config_dir,
        _load_backend_factories(),
    )
    if not specs:
        raise RuntimeError(
            "No backend service is enabled in app-backend configuration."
        )

    for spec in specs:
        with _backend_config_scope(spec.config_file):
            backend_app = spec.factory()
        backends.append(BackendRuntime(spec=spec, app=backend_app))

    # Route the most specific prefix first.
    backends.sort(key=lambda item: len(item.spec.path_prefix), reverse=True)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with AsyncExitStack() as stack:
            for backend in backends:
                await stack.enter_async_context(
                    backend.app.router.lifespan_context(backend.app)
                )
            for backend in backends:
                backend.client = await stack.enter_async_context(
                    AsyncClient(
                        transport=ASGITransport(app=backend.app),
                        base_url="http://fred.local",
                    )
                )
            app.state.backends = backends
            yield

    docs_url = "/docs" if configuration.app.docs_enabled else None
    redoc_url = "/redoc" if configuration.app.docs_enabled else None
    openapi_url = "/openapi.json" if configuration.app.docs_enabled else None

    app = FastAPI(
        title=configuration.app.name,
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
        lifespan=lifespan,
    )

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "service": "app-backend"}

    @app.get("/ready")
    async def ready() -> dict[str, str]:
        return {"status": "ready", "service": "app-backend"}

    @app.get("/")
    async def index() -> dict[str, object]:
        return {
            "service": "app-backend",
            "mode": "single-process",
            "routes": [backend.spec.path_prefix for backend in backends],
        }

    @app.api_route("/{path:path}", methods=FORWARDED_METHODS)
    async def proxy(request: Request, path: str) -> Response:
        del path
        backend = _find_backend(request.url.path, request.app.state.backends)
        if backend is None:
            available_prefixes = ", ".join(
                backend.spec.path_prefix for backend in request.app.state.backends
            )
            raise HTTPException(
                status_code=404,
                detail=f"Unknown route prefix. Available prefixes: {available_prefixes}",
            )
        return await _proxy_request(request, backend)

    return app
