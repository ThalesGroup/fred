from __future__ import annotations

from types import SimpleNamespace

from fred_agents import __main__ as entrypoint


def test_main_passes_limit_concurrency_to_uvicorn(monkeypatch) -> None:
    """
    Ensure local pod startup forwards the optional Uvicorn connection cap.

    Why this test exists:
    - the rate-limiter port keeps the runtime behavior in YAML config while
      `python -m fred_agents` still owns the actual Uvicorn startup call

    How to use it:
    - run via the default offline `fred-agents` test suite

    Example:
    - `pytest tests/test_entrypoint.py -q`
    """

    config = SimpleNamespace(
        app=SimpleNamespace(
            port=8123,
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
        "host": "127.0.0.1",
        "port": 8123,
        "limit_concurrency": 41,
        "reload": True,
    }
