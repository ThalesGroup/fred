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

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import build_backend
import pytest


def _write_catalog(path: Path, *, revision: str | None = None) -> None:
    """Write the smallest valid catalog used by isolated backend-hook tests.

    Pass ``revision`` to deliberately create a catalog with a chosen revision.
    """

    content: dict[str, Any] = {"schema_version": "1", "items": []}
    canonical = json.dumps(
        content,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    content["catalog_revision"] = revision or (
        f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()}"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{json.dumps(content)}\n", encoding="utf-8")


@pytest.mark.parametrize(
    ("hook_name", "backend_hook_name"),
    [
        ("build_wheel", "build_wheel"),
        ("build_sdist", "build_sdist"),
        ("build_editable", "build_editable"),
    ],
)
def test_artifact_build_hooks_materialize_catalog_first(
    monkeypatch: pytest.MonkeyPatch,
    hook_name: str,
    backend_hook_name: str,
) -> None:
    """Keep every supported artifact hook from packaging a stale catalog.

    The parameterized check invokes each public hook and asserts generation is
    ordered before its matching setuptools delegate.
    """

    calls: list[str] = []
    monkeypatch.setattr(
        build_backend,
        "_materialize_application_catalog",
        lambda: calls.append("catalog"),
    )
    monkeypatch.setattr(
        build_backend._setuptools_backend,
        backend_hook_name,
        lambda *_args, **_kwargs: calls.append("artifact") or "artifact-name",
    )

    artifact = getattr(build_backend, hook_name)("output")

    assert artifact == "artifact-name"
    assert calls == ["catalog", "artifact"]


def test_source_distribution_catalog_is_reused_without_monorepo_generator(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Allow an extracted source distribution to build outside the monorepo.

    Point the backend at a valid embedded catalog and an absent generator, then
    materialize it using the same path exercised by artifact hooks.
    """

    catalog_path = tmp_path / "catalog.generated.json"
    _write_catalog(catalog_path)
    monkeypatch.setattr(build_backend, "_CATALOG_PATH", catalog_path)
    monkeypatch.setattr(build_backend, "_GENERATOR_PATH", tmp_path / "missing.mjs")

    build_backend._materialize_application_catalog()


def test_source_checkout_invokes_catalog_generator(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Ensure source-checkout builds invoke the focused Node generator.

    Substitute a temporary checkout and capture the fixed command, working
    directory, and generated catalog before validation.
    """

    frontend_directory = tmp_path / "frontend"
    generator_path = frontend_directory / "generate-applications.mjs"
    generator_path.parent.mkdir(parents=True)
    generator_path.write_text("", encoding="utf-8")
    catalog_path = tmp_path / "catalog.generated.json"
    monkeypatch.setattr(build_backend, "_FRONTEND_DIRECTORY", frontend_directory)
    monkeypatch.setattr(build_backend, "_GENERATOR_PATH", generator_path)
    monkeypatch.setattr(build_backend, "_CATALOG_PATH", catalog_path)
    monkeypatch.setattr(build_backend.shutil, "which", lambda _command: "/usr/bin/node")

    def generate(command: list[str], *, cwd: Path, check: bool) -> None:
        """Emulate the Node generator while asserting its safe invocation."""

        assert command == [
            "/usr/bin/node",
            str(generator_path),
            "--control-plane-only",
        ]
        assert cwd == frontend_directory
        assert check is True
        _write_catalog(catalog_path)

    monkeypatch.setattr(build_backend.subprocess, "run", generate)

    build_backend._materialize_application_catalog()


def test_packaged_catalog_rejects_invalid_revision(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Prevent packaging when catalog content and revision disagree.

    Write a deliberately invalid revision and validate it through the backend's
    packaged-catalog guard.
    """

    catalog_path = tmp_path / "catalog.generated.json"
    _write_catalog(catalog_path, revision=f"sha256:{'0' * 64}")
    monkeypatch.setattr(build_backend, "_CATALOG_PATH", catalog_path)

    with pytest.raises(RuntimeError, match="revision is invalid"):
        build_backend._validate_catalog()
