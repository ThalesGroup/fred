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
Guards for the PEP 562 lazy surfaces of `fred_sdk` and `fred_sdk.contracts`.

A lazy `__getattr__` turns what used to be an import-time error into a runtime
one, so these tests resolve every exported name and keep `_LAZY` and `__all__`
from drifting apart.
"""

import importlib
import subprocess  # nosec B404 — fixed argv, no shell; needed for a fresh interpreter
import sys
from types import ModuleType

import fred_sdk
import fred_sdk.contracts
import pytest

_MODULES = [fred_sdk, fred_sdk.contracts]
_MODULE_IDS = ["fred_sdk", "fred_sdk.contracts"]

# Heavy trees a lean Knowledge Base pod must never drag in. `google.cloud` is
# planted in sys.modules at startup by google-cloud-aiplatform's nspkg .pth, so
# seeing it there is an environment artifact rather than a fred_sdk import.
_FORBIDDEN_TOP_LEVEL = (
    "fred_core",
    "langchain",
    "langgraph",
    "pandas",
    "sqlalchemy",
    "fastapi",
    "minio",
    "opensearchpy",
    "google.cloud",
)


def _exported(module: ModuleType) -> list[str]:
    names: list[str] = getattr(module, "__all__")
    return names


def _lazy_map(module: ModuleType) -> dict[str, str]:
    mapping: dict[str, str] = getattr(module, "_LAZY")
    return mapping


@pytest.mark.parametrize("module", _MODULES, ids=_MODULE_IDS)
def test_every_exported_name_resolves(module: ModuleType) -> None:
    unresolved: list[str] = []
    for name in _exported(module):
        try:
            value = getattr(module, name)
        except AttributeError as exc:
            unresolved.append(f"{name}: {exc}")
            continue
        if value is None:
            unresolved.append(f"{name}: resolved to None")
    assert not unresolved, (
        f"{module.__name__} exports that did not resolve: {unresolved}"
    )


@pytest.mark.parametrize("module", _MODULES, ids=_MODULE_IDS)
def test_lazy_map_covers_all_exactly(module: ModuleType) -> None:
    lazy_keys = set(_lazy_map(module))
    exported = set(_exported(module))
    assert sorted(lazy_keys - exported) == [], "stale _LAZY entries absent from __all__"
    assert sorted(exported - lazy_keys) == [], "__all__ names missing from _LAZY"


@pytest.mark.parametrize("module", _MODULES, ids=_MODULE_IDS)
def test_unknown_attribute_raises_attribute_error(module: ModuleType) -> None:
    with pytest.raises(AttributeError):
        _ = getattr(module, "NoSuchExportedName")


@pytest.mark.parametrize("module", _MODULES, ids=_MODULE_IDS)
def test_dir_lists_the_public_surface(module: ModuleType) -> None:
    assert set(_exported(module)) <= set(dir(module))


@pytest.mark.parametrize(
    ("module", "submodule"),
    [(fred_sdk, "knowledge_base"), (fred_sdk.contracts, "models")],
    ids=_MODULE_IDS,
)
def test_dir_lists_imported_submodules(module: ModuleType, submodule: str) -> None:
    # dir() must show what a normal package shows: not only the lazy surface but
    # also submodules already imported by name, or the lazy shim is a regression.
    importlib.import_module(f"{module.__name__}.{submodule}")
    assert submodule in dir(module)


def test_knowledge_base_import_stays_lean() -> None:
    # A fresh interpreter is the only honest probe: import side effects do not
    # unwind, so the test session's own imports would mask the leak. Only what
    # this import ADDS counts — a .pth file can plant a namespace package first.
    probe = (
        "import sys\n"
        f"forbidden = {_FORBIDDEN_TOP_LEVEL!r}\n"
        "resident = {m for m in forbidden if m in sys.modules}\n"
        "import fred_sdk.knowledge_base\n"
        "leaked = (m for m in forbidden if m in sys.modules and m not in resident)\n"
        "print(','.join(sorted(leaked)))\n"
    )
    result = subprocess.run(  # nosec B603 — fixed argv, no shell
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"probe interpreter failed:\n{result.stderr}"
    loaded = [m for m in result.stdout.strip().split(",") if m]
    assert not loaded, f"import fred_sdk.knowledge_base pulled in: {loaded}"
