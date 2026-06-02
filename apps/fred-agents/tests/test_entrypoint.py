from __future__ import annotations

from types import SimpleNamespace

from fred_agents import __main__ as entrypoint


def test_main_passes_http_binding_settings_to_uvicorn(monkeypatch) -> None:
    """
    Ensure startup forwards the configured bind settings and keeps reload disabled.

    Why this test exists:
        - container and local launches both rely on `python -m fred_agents`
            honoring the YAML host/port/log-level contract
        - production pods must not run with Uvicorn auto-reload enabled

    How to use it:
    - run via the default offline `fred-agents` test suite

    Example:
    - `pytest tests/test_entrypoint.py -q`
    """

    config = SimpleNamespace(
        app=SimpleNamespace(
            host="0.0.0.0",
            port=8123,
            log_level="warning",
            limit_concurrency=41,
        )
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(entrypoint, "load_agent_pod_config", lambda: config)

    def _fake_uvicorn_run(app_path: str, **kwargs: object) -> None:
        captured["app_path"] = app_path
        captured.update(kwargs)

    monkeypatch.setattr(entrypoint.uvicorn, "run", _fake_uvicorn_run)

    entrypoint.main()

    assert captured == {
        "app_path": "fred_agents.main:app",
        "host": "0.0.0.0",
        "port": 8123,
        "log_level": "warning",
        "limit_concurrency": 41,
        "reload": False,
    }
