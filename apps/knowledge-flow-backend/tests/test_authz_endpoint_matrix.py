from __future__ import annotations

import ast
from pathlib import Path
from typing import cast

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BACKEND_ROOT = Path(__file__).resolve().parents[1] / "knowledge_flow_backend"
_MATRIX_PATH = _REPO_ROOT / "docs/swift/platform/authz-endpoint-matrix.yaml"
_BASE_URL = "/knowledge-flow/v1"
_HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


def _matrix_operations(service: str) -> set[tuple[str, str]]:
    """Load the reviewed endpoint ledger for one service.

    How to use it:
    - call from endpoint coverage tests before comparing against route inventory.
    - keep authorization decisions in the matrix, not duplicated in test code.
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
        assert isinstance(entry.get("required_permission"), str), f"Matrix entry has non-string required_permission: {entry!r}"
        selected.add((method.upper(), path))

    assert selected, f"No endpoint matrix entries found for service {service!r}"
    return selected


def _literal_string(value: ast.expr) -> str | None:
    """Return a literal string from an AST expression when the route is static."""
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        return value.value
    return None


def _router_prefixes(tree: ast.AST) -> dict[str, str]:
    """Find local `APIRouter(prefix=...)` variables in one module.

    How to use it:
    - pair with `_declared_route_operations` to account for nested routers such
      as `APIRouter(prefix="/dev/bench")`.
    - only literal prefixes are included; dynamic route registration must be
      added to the matrix with a focused test.
    """
    prefixes = {"router": ""}

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        func = node.value.func
        if not isinstance(func, ast.Name) or func.id != "APIRouter":
            continue

        prefix = ""
        for keyword in node.value.keywords:
            if keyword.arg == "prefix":
                prefix = _literal_string(keyword.value) or ""

        for target in node.targets:
            if isinstance(target, ast.Name):
                prefixes[target.id] = prefix

    return prefixes


def _declared_route_operations() -> set[tuple[str, str]]:
    """Return statically declared knowledge-flow FastAPI route operations.

    How to use it:
    - compare against `authz-endpoint-matrix.yaml` without building the full app.
    - this intentionally avoids heavyweight startup paths that create vector
      stores or load local ML models during a default unit test.
    """
    operations: set[tuple[str, str]] = set()

    for source_path in _BACKEND_ROOT.rglob("*.py"):
        tree = ast.parse(source_path.read_text(), filename=str(source_path))
        prefixes = _router_prefixes(tree)

        for node in ast.walk(tree):
            if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call):
                    continue
                if not isinstance(decorator.func, ast.Attribute):
                    continue
                method = decorator.func.attr
                if method not in _HTTP_METHODS:
                    continue
                receiver = decorator.func.value
                if not isinstance(receiver, ast.Name):
                    continue
                if receiver.id not in prefixes and receiver.id != "app":
                    continue

                route_path = None
                if decorator.args:
                    route_path = _literal_string(decorator.args[0])
                for keyword in decorator.keywords:
                    if keyword.arg == "path":
                        route_path = _literal_string(keyword.value)
                if route_path is None:
                    continue

                if receiver.id == "app":
                    full_path = route_path
                else:
                    full_path = f"{_BASE_URL}{prefixes.get(receiver.id, '')}{route_path}"
                operations.add((method.upper(), full_path))

    assert operations, "No knowledge-flow route operations found"
    return operations


def _format_operations(operations: set[tuple[str, str]]) -> str:
    return "\n".join(f"- {method} {path}" for method, path in sorted(operations))


def test_knowledge_flow_endpoint_matrix_covers_all_declared_routes() -> None:
    """Every knowledge-flow route must have an explicit authorization review row."""
    declared_routes = _declared_route_operations()
    matrix_routes = _matrix_operations("knowledge-flow")

    missing = declared_routes - matrix_routes
    stale = matrix_routes - declared_routes

    assert not missing, "Add these declared routes to authz-endpoint-matrix.yaml:\n" + _format_operations(missing)
    assert not stale, "Remove or update these stale matrix routes:\n" + _format_operations(stale)
