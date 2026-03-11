import asyncio
from contextlib import AsyncExitStack

from fastapi import APIRouter, FastAPI
from fastapi.dependencies.utils import solve_dependencies
from fastapi.routing import APIRoute
from fred_core import KeycloakUser, get_current_user
from starlette.requests import Request
from starlette.responses import Response

from agentic_backend.core.feedback import feedback_controller


class _FakeFeedbackService:
    last_store = None
    last_feedback = None

    def __init__(self, store):
        self.store = store
        type(self).last_store = store

    async def add_feedback(self, user, feedback):
        type(self).last_feedback = feedback


def _build_app() -> FastAPI:
    async def _fake_current_user() -> KeycloakUser:
        return KeycloakUser(
            uid="u-1", username="tester", email="t@example.com", roles=["user"]
        )

    app = FastAPI()
    router = APIRouter(prefix="/agentic/v1")
    router.include_router(feedback_controller.router)
    app.include_router(router)
    app.dependency_overrides[get_current_user] = _fake_current_user
    return app


def _get_post_feedback_route() -> APIRoute:
    for route in feedback_controller.router.routes:
        if isinstance(route, APIRoute) and route.endpoint.__name__ == "post_feedback":
            return route
    raise AssertionError("post_feedback route not found")


def test_feedback_post_route_uses_async_dependency(monkeypatch):
    async def _run() -> None:
        sentinel_store = object()

        def _fake_get_feedback_store():
            asyncio.get_running_loop()
            return sentinel_store

        monkeypatch.setattr(
            feedback_controller, "get_feedback_store", _fake_get_feedback_store
        )
        monkeypatch.setattr(
            feedback_controller, "FeedbackService", _FakeFeedbackService
        )

        app = _build_app()
        route = _get_post_feedback_route()
        request = Request(
            {
                "type": "http",
                "http_version": "1.1",
                "method": "POST",
                "scheme": "http",
                "path": "/agentic/v1/chatbot/feedback",
                "raw_path": b"/agentic/v1/chatbot/feedback",
                "query_string": b"",
                "headers": [],
                "client": ("testclient", 50000),
                "server": ("testserver", 80),
                "path_params": {},
                "app": app,
            }
        )

        async with AsyncExitStack() as stack:
            solved = await solve_dependencies(
                request=request,
                dependant=route.dependant,
                body={
                    "rating": 4,
                    "comment": "ok",
                    "message_id": "message-1",
                    "session_id": "session-1",
                    "agent_id": "agent-1",
                },
                response=Response(),
                dependency_overrides_provider=app,
                dependency_cache=None,
                async_exit_stack=stack,
                embed_body_fields=getattr(route, "_embed_body_fields", False),
            )

            assert solved.errors == []
            result = await route.endpoint(**solved.values)

        assert result is None
        assert _FakeFeedbackService.last_store is sentinel_store
        assert _FakeFeedbackService.last_feedback is not None
        assert _FakeFeedbackService.last_feedback.message_id == "message-1"
        assert _FakeFeedbackService.last_feedback.agent_id == "agent-1"

    asyncio.run(_run())
