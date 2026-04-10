import asyncio

from fastapi import APIRouter, FastAPI
from fred_core import KeycloakUser, get_current_user
from httpx import ASGITransport, AsyncClient

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

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                "/agentic/v1/chatbot/feedback",
                json={
                    "rating": 4,
                    "comment": "ok",
                    "message_id": "message-1",
                    "session_id": "session-1",
                    "agent_id": "agent-1",
                },
            )

        assert response.status_code == 204
        assert _FakeFeedbackService.last_store is sentinel_store
        assert _FakeFeedbackService.last_feedback is not None
        assert _FakeFeedbackService.last_feedback.message_id == "message-1"
        assert _FakeFeedbackService.last_feedback.agent_id == "agent-1"

    asyncio.run(_run())
