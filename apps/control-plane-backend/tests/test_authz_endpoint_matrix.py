from __future__ import annotations

from pathlib import Path
from typing import cast

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MATRIX_PATH = _REPO_ROOT / "docs/swift/platform/authz-endpoint-matrix.yaml"
_HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


def _matrix_operations(service: str) -> set[tuple[str, str]]:
    """Load the reviewed endpoint ledger for one service.

    How to use it:
    - call from endpoint coverage tests before comparing against OpenAPI.
    - keep the matrix human-owned; tests only prove route coverage.
    """
    payload = cast(dict[str, object], yaml.safe_load(_MATRIX_PATH.read_text()))
    operations = cast(list[dict[str, object]], payload["operations"])
    selected: set[tuple[str, str]] = set()

    for entry in operations:
        if entry.get("service") != service:
            continue
        method = entry.get("method")
        path = entry.get("path")
        assert isinstance(method, str), f"Matrix entry has non-string method: {entry!r}"
        assert isinstance(path, str), f"Matrix entry has non-string path: {entry!r}"
        assert entry.get("review_status") in {
            "pending_review",
            "approved",
            "external_or_public",
        }, f"Matrix entry has invalid review_status: {entry!r}"
        assert isinstance(entry.get("required_permission"), str), (
            f"Matrix entry has non-string required_permission: {entry!r}"
        )
        selected.add((method.upper(), path))

    assert selected, f"No endpoint matrix entries found for service {service!r}"
    return selected


def _control_plane_openapi_operations(monkeypatch) -> set[tuple[str, str]]:
    """Return the actual control-plane HTTP operations published by OpenAPI.

    How to use it:
    - keep this test on `configuration_test.yaml` so it remains infrastructure-free.
    - compare only method/path; permission semantics are reviewed in focused tests.
    """
    monkeypatch.setenv("CONFIG_FILE", "./config/configuration_test.yaml")

    from control_plane_backend.main import create_app

    schema = create_app().openapi()
    paths = cast(dict[str, dict[str, object]], schema["paths"])
    return {
        (method.upper(), path)
        for path, methods in paths.items()
        for method in methods
        if method in _HTTP_METHODS
    }


def _format_operations(operations: set[tuple[str, str]]) -> str:
    return "\n".join(f"- {method} {path}" for method, path in sorted(operations))


def test_control_plane_endpoint_matrix_covers_all_openapi_operations(
    monkeypatch,
) -> None:
    """Every control-plane route must have an explicit authorization review row."""
    published = _control_plane_openapi_operations(monkeypatch)
    declared = _matrix_operations("control-plane")

    missing = published - declared
    stale = declared - published

    assert not missing, (
        "Add these published routes to authz-endpoint-matrix.yaml:\n"
        + _format_operations(missing)
    )
    assert not stale, (
        "Remove or update these stale matrix routes:\n" + _format_operations(stale)
    )
