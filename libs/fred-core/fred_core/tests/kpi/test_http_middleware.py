# Copyright Thales 2026
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

"""
Offline unit tests for fred_core.kpi.http_middleware.KPIMiddleware.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from fred_core.kpi.http_middleware import KPIMiddleware
from fred_core.kpi.noop_kpi_writer import NoOpKPIWriter


def _make_app(kpi=None) -> tuple[FastAPI, MagicMock]:
    """Return a minimal FastAPI app with KPIMiddleware and a mock api_call spy."""
    app = FastAPI()
    writer = kpi or NoOpKPIWriter()
    spy = MagicMock(wraps=writer.api_call)
    writer.api_call = spy
    app.add_middleware(KPIMiddleware, kpi=writer)

    @app.get("/ok")
    def ok():
        return {"status": "ok"}

    @app.get("/healthz")
    def healthz():
        return {"alive": True}

    @app.get("/api/v1/ready")
    def ready():
        return {"ready": True}

    @app.get("/error")
    def error():
        raise ValueError("boom")

    return app, spy


class TestKPIMiddlewareEmitsMetric:
    def setup_method(self) -> None:
        self.app, self.spy = _make_app()
        self.client = TestClient(self.app, raise_server_exceptions=False)

    def test_api_call_invoked_on_normal_request(self) -> None:
        self.client.get("/ok")
        self.spy.assert_called_once()

    def test_route_is_templated_path(self) -> None:
        self.client.get("/ok")
        kwargs = self.spy.call_args.kwargs
        assert kwargs["route"] == "/ok"

    def test_method_is_uppercased(self) -> None:
        self.client.get("/ok")
        kwargs = self.spy.call_args.kwargs
        assert kwargs["method"] == "GET"

    def test_http_status_200_on_success(self) -> None:
        self.client.get("/ok")
        kwargs = self.spy.call_args.kwargs
        assert kwargs["http_status"] == 200

    def test_latency_ms_is_positive(self) -> None:
        self.client.get("/ok")
        kwargs = self.spy.call_args.kwargs
        assert kwargs["latency_ms"] > 0

    def test_unauthenticated_actor_is_system_with_anonymous_dim(self) -> None:
        self.client.get("/ok")
        kwargs = self.spy.call_args.kwargs
        assert kwargs["actor"].type == "system"
        assert kwargs["extra_dims"] == {"actor_subtype": "anonymous"}

    def test_authenticated_actor_is_human(self) -> None:
        fake_user = MagicMock()
        fake_user.uid = "user-123"
        with patch("fred_core.kpi.http_middleware.decode_jwt", return_value=fake_user):
            self.client.get("/ok", headers={"Authorization": "Bearer fake.token.here"})
        kwargs = self.spy.call_args.kwargs
        assert kwargs["actor"].type == "human"
        assert kwargs["actor"].user_id == "user-123"
        assert kwargs["extra_dims"] is None

    def test_500_status_on_unhandled_exception(self) -> None:
        self.client.get("/error")
        kwargs = self.spy.call_args.kwargs
        assert kwargs["http_status"] == 500


class TestKPIMiddlewareTeamAttribution:
    def setup_method(self) -> None:
        self.app, self.spy = _make_app()

        @self.app.get("/teams/{team_id}/ping")
        def team_ping(team_id: str):
            return {"team_id": team_id}

        self.client = TestClient(self.app, raise_server_exceptions=False)

    def _get_as_user(self, path: str) -> None:
        fake_user = MagicMock()
        fake_user.uid = "user-123"
        with patch("fred_core.kpi.http_middleware.decode_jwt", return_value=fake_user):
            self.client.get(path, headers={"Authorization": "Bearer fake.token.here"})

    def test_team_route_tags_team_id_from_path(self) -> None:
        self._get_as_user("/teams/team-a/ping")
        kwargs = self.spy.call_args.kwargs
        assert kwargs["route"] == "/teams/{team_id}/ping"
        assert kwargs["extra_dims"] == {"team_id": "team-a"}

    def test_refused_team_route_has_no_team_dim(self) -> None:
        @self.app.get("/teams/{team_id}/secret")
        def team_secret(team_id: str):
            raise HTTPException(status_code=403, detail="forbidden")

        self._get_as_user("/teams/someone-else/secret")
        assert self.spy.call_args.kwargs["http_status"] == 403
        assert self.spy.call_args.kwargs["extra_dims"] is None

    def test_route_without_team_has_no_team_dim(self) -> None:
        self._get_as_user("/ok")
        assert self.spy.call_args.kwargs["extra_dims"] is None

    def test_anonymous_team_route_has_no_team_dim(self) -> None:
        self.client.get("/teams/team-a/ping")
        assert self.spy.call_args.kwargs["extra_dims"] == {"actor_subtype": "anonymous"}

    def test_team_id_is_never_a_prometheus_label(self) -> None:
        from fred_core.kpi.prometheus_kpi_store import PROMETHEUS_ALLOWED_LABELS

        assert "team_id" not in PROMETHEUS_ALLOWED_LABELS


class TestKPIMiddlewareSkipPaths:
    def setup_method(self) -> None:
        self.app, self.spy = _make_app()
        self.client = TestClient(self.app, raise_server_exceptions=False)

    def test_healthz_not_emitted(self) -> None:
        self.client.get("/healthz")
        self.spy.assert_not_called()

    def test_ready_suffix_not_emitted(self) -> None:
        self.client.get("/api/v1/ready")
        self.spy.assert_not_called()


class TestKPIMiddlewareFailSafe:
    def test_kpi_failure_does_not_abort_request(self) -> None:
        app = FastAPI()
        broken_writer = NoOpKPIWriter()
        broken_writer.api_call = MagicMock(side_effect=RuntimeError("store down"))
        app.add_middleware(KPIMiddleware, kpi=broken_writer)

        @app.get("/ping")
        def ping():
            return {"pong": True}

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/ping")
        assert response.status_code == 200


class TestKPIMiddlewareLazyWriter:
    def test_callable_source_is_resolved_per_request(self) -> None:
        writer = NoOpKPIWriter()
        spy = MagicMock(wraps=writer.api_call)
        writer.api_call = spy

        app = FastAPI()
        # Lazy callable — simulates lifespan-initialised writer
        app.add_middleware(KPIMiddleware, kpi=lambda: writer)

        @app.get("/lazy")
        def lazy():
            return {}

        client = TestClient(app)
        client.get("/lazy")
        spy.assert_called_once()
