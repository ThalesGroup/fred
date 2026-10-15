#!/usr/bin/env python3
"""Prepare independently versioned Fred Python packages for a code release."""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATCH = re.compile(r"(\d+)\.(\d+)\.(\d+)")
PROJECT_TABLE = re.compile(r"^\[project\]\n(.*?)(?=^\[|\Z)", re.M | re.S)
PROJECT_VERSION = re.compile(r'^version = "[^"]*"$', re.M)
SHARED = ("fred-core", "fred-sdk", "fred-runtime")
POD = "fred-pod"
IGNORED_PARTS = {"target", ".venv", "__pycache__", "node_modules"}


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, text=True, capture_output=True, check=False
    )
    if result.returncode:
        raise ValueError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout.strip()


def package_dir(root: Path, name: str) -> Path:
    if name in (*SHARED, POD):
        return root / "libs" / name
    if re.fullmatch(r"fred-capability-[a-z0-9-]+", name):
        return root / "libs" / "capabilities" / name
    raise ValueError(f"Unknown Fred package: {name}")


def project(path: Path) -> dict[str, object]:
    return tomllib.loads(path.read_text())["project"]


def patch_after(value: str) -> str:
    match = PATCH.fullmatch(value)
    if match is None:
        raise ValueError(f"Expected a stable X.Y.Z package version, got {value!r}")
    return f"{match[1]}.{match[2]}.{int(match[3]) + 1}"


def tagged_text(root: Path, base: str, relative: Path) -> str | None:
    result = subprocess.run(
        ["git", "show", f"{base}:{relative.as_posix()}"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout if result.returncode == 0 else None


def baseline(root: Path, base: str) -> None:
    if not re.fullmatch(r"code/v\d+\.\d+\.\d+", base):
        raise ValueError("--base must be a stable code/vX.Y.Z tag")
    git(root, "rev-parse", "--verify", "--end-of-options", f"{base}^{{commit}}")
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", base, "HEAD"], cwd=root, check=False
    )
    if result.returncode:
        raise ValueError(f"{base} is not an ancestor of HEAD")


def version_plan(root: Path, base: str, names: set[str]) -> dict[str, str]:
    versions: dict[str, str] = {}
    for name in sorted(names):
        path = package_dir(root, name) / "pyproject.toml"
        if not path.is_file() or project(path)["name"] != name:
            raise ValueError(f"Missing or mismatched package: {path}")
        previous_text = tagged_text(root, base, path.relative_to(root))
        current = str(project(path)["version"])
        if previous_text is None:
            if name in SHARED:
                raise ValueError(f"{name} did not exist at {base}")
            versions[name] = current
            continue
        previous = str(tomllib.loads(previous_text)["project"]["version"])
        target = patch_after(previous)
        if current not in (previous, target):
            raise ValueError(
                f"{name}: current {current} differs from both tagged {previous} "
                f"and prepared {target}; review independent publication"
            )
        versions[name] = target
    return versions


def release_change_paths(root: Path, base: str) -> set[Path]:
    tracked = git(root, "diff", "--name-only", base, "--", "libs").splitlines()
    untracked = git(
        root, "ls-files", "--others", "--exclude-standard", "--", "libs"
    ).splitlines()
    return {Path(path) for path in (*tracked, *untracked)}


def substantive_pyproject_change(root: Path, base: str, relative: Path) -> bool:
    before = tagged_text(root, base, relative)
    if before is None:
        return True
    after = (root / relative).read_text()

    def without_release_coordinates(value: str) -> str:
        return PROJECT_VERSION.sub('version = "<release>"', value, count=1)

    return without_release_coordinates(before) != without_release_coordinates(after)


def candidates(root: Path, base: str) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for relative in sorted(release_change_paths(root, base)):
        if IGNORED_PARTS & set(relative.parts) or relative.name == "uv.lock":
            continue
        parts = relative.parts
        if len(parts) >= 4 and parts[:2] == ("libs", "capabilities"):
            name = parts[2]
        elif len(parts) >= 3 and parts[:2] == ("libs", POD):
            name = POD
        else:
            continue
        if relative.name == "pyproject.toml" and not substantive_pyproject_change(
            root, base, relative
        ):
            continue
        result.setdefault(name, []).append(relative.as_posix())
    return result


def rewrite(text: str, version: str, floors: dict[str, str]) -> str:
    """Set one project's version and only selected internal dependency floors."""
    table = PROJECT_TABLE.search(text)
    if table is None or not PROJECT_VERSION.search(table.group(1)):
        raise ValueError('no `version = "..."` line in [project]')
    body = PROJECT_VERSION.sub(f'version = "{version}"', table.group(1), count=1)
    text = text[: table.start(1)] + body + text[table.end(1) :]
    if not floors:
        return text
    alternatives = "|".join(
        re.escape(name) for name in sorted(floors, key=len, reverse=True)
    )
    requirement = re.compile(rf'"({alternatives})(\[[^\]"]*\])?([<>=!~][^"]*)"')

    def floor(match: re.Match[str]) -> str:
        name, extras, specifier = match.group(1), match.group(2) or "", match.group(3)
        if not re.fullmatch(r">=\s*[^,;\s]+", specifier):
            raise ValueError(
                f"{name}{extras}{specifier}: only a single `>=` floor is rewritten"
            )
        old_floor = specifier[2:].strip()
        if PATCH.fullmatch(old_floor) is None:
            raise ValueError(f"{name}{extras}{specifier}: expected a stable floor")
        if tuple(map(int, old_floor.split("."))) > tuple(
            map(int, floors[name].split("."))
        ):
            raise ValueError(
                f"{name}{extras}{specifier}: floor exceeds prepared {floors[name]}"
            )
        return f'"{name}{extras}>={floors[name]}"'

    return requirement.sub(floor, text)


def manifest_version(text: str) -> tuple[str, int]:
    found: list[tuple[str, int]] = []
    for node in ast.walk(ast.parse(text)):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id != "CapabilityManifest":
            continue
        for keyword in node.keywords:
            if keyword.arg == "version" and isinstance(keyword.value, ast.Constant):
                value = keyword.value.value
                if isinstance(value, str):
                    found.append((value, keyword.value.lineno))
    if len(found) != 1:
        raise ValueError(
            "Expected exactly one literal CapabilityManifest.version in each selected file"
        )
    return found[0]


def manifest_candidates(root: Path, packages: set[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for name in sorted(packages):
        if not name.startswith("fred-capability-"):
            continue
        for path in package_dir(root, name).rglob("*.py"):
            if IGNORED_PARTS & set(path.parts) or "tests" in path.parts:
                continue
            content = path.read_text()
            if "CapabilityManifest(" not in content:
                continue
            version, _ = manifest_version(content)
            result[path.relative_to(root).as_posix()] = version
    return result


def rewrite_manifest(text: str, previous: str, target: str) -> str:
    current, line_number = manifest_version(text)
    if current not in (previous, target):
        raise ValueError(
            f"Manifest version {current} differs from tagged {previous} and prepared {target}"
        )
    lines = text.splitlines(keepends=True)
    line = lines[line_number - 1]
    replacement = line.replace(f'"{current}"', f'"{target}"', 1)
    if replacement == line and current != target:
        raise ValueError("Cannot rewrite the selected manifest version literal")
    lines[line_number - 1] = replacement
    return "".join(lines)


def lock_dirs(root: Path, names: set[str]) -> list[Path]:
    locks = sorted(
        [*(root / "libs").rglob("uv.lock"), *(root / "apps").rglob("uv.lock")]
    )
    result = []
    for lock in locks:
        if IGNORED_PARTS & set(lock.relative_to(root).parts):
            continue
        data = tomllib.loads(lock.read_text())
        if any(
            package.get("name") in names and "editable" in package.get("source", {})
            for package in data.get("package", [])
        ):
            result.append(lock.parent)
    return result


def editable_versions(lock: Path, names: set[str]) -> dict[str, str]:
    data = tomllib.loads(lock.read_text())
    return {
        str(package["name"]): str(package["version"])
        for package in data.get("package", [])
        if package.get("name") in names and "editable" in package.get("source", {})
    }


def verify_locks(
    projects: list[Path],
    versions: dict[str, str],
    expected: dict[Path, set[str]] | None = None,
) -> None:
    for directory in projects:
        actual = editable_versions(directory / "uv.lock", set(versions))
        for name in expected[directory] if expected is not None else actual:
            if name not in actual:
                raise ValueError(f"{directory / 'uv.lock'}: missing local {name}")
            if actual[name] != versions[name]:
                raise ValueError(
                    f"{directory / 'uv.lock'}: {name} is {actual[name]}, "
                    f"expected {versions[name]}"
                )


def prepare(
    root: Path,
    base: str,
    capabilities: set[str],
    manifests: set[Path],
    include_pod: bool,
    *,
    apply: bool,
) -> dict[str, object]:
    baseline(root, base)
    changed = candidates(root, base)
    selected = set(SHARED) | capabilities | ({POD} if include_pod else set())
    if invalid := capabilities - set(changed):
        raise ValueError(
            f"Selected capabilities have no source change: {', '.join(sorted(invalid))}"
        )
    if include_pod and POD not in changed:
        raise ValueError("fred-pod has no source change")
    if apply and (
        unselected := (set(changed) - capabilities - ({POD} if include_pod else set()))
    ):
        raise ValueError(
            f"Changed packages need explicit selection: {', '.join(sorted(unselected))}"
        )
    versions = version_plan(root, base, selected)
    paths: dict[Path, str] = {}
    for name in selected:
        path = package_dir(root, name) / "pyproject.toml"
        floors = {
            dependency: version
            for dependency, version in versions.items()
            if dependency != name
        }
        paths[path] = rewrite(path.read_text(), versions[name], floors)

    manifest_targets: dict[str, str] = {}
    for relative in sorted(manifests):
        path = (root / relative).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            raise ValueError(f"Invalid manifest path: {relative}")
        owner = next(
            (
                name
                for name in capabilities
                if path.is_relative_to(package_dir(root, name))
            ),
            None,
        )
        if owner is None:
            raise ValueError(
                f"Selected manifest must belong to a selected capability: {relative}"
            )
        current, _ = manifest_version(path.read_text())
        prior_text = tagged_text(root, base, path.relative_to(root))
        if prior_text is None:
            target = current
        else:
            previous, _ = manifest_version(prior_text)
            target = patch_after(previous)
            paths[path] = rewrite_manifest(path.read_text(), previous, target)
        manifest_targets[relative.as_posix()] = target

    for chart, name in (("agent-pod", "fred-runtime"), ("knowledge-base", "fred-sdk")):
        path = root / "deploy" / "charts" / chart / "Chart.yaml"
        if not path.is_file():
            raise ValueError(f"Missing pod chart: {path}")
        updated, count = re.subn(
            r"^appVersion: .*$",
            f'appVersion: "{versions[name]}"',
            path.read_text(),
            count=1,
            flags=re.M,
        )
        if count != 1:
            raise ValueError(f"Missing appVersion in {path}")
        paths[path] = updated

    locks = lock_dirs(root, selected)
    expected_locks = {
        directory: set(editable_versions(directory / "uv.lock", selected))
        for directory in locks
    }
    unchanged_capabilities = {
        path.parent.name: str(project(path)["version"])
        for path in sorted((root / "libs" / "capabilities").glob("*/pyproject.toml"))
        if path.parent.name not in capabilities and path.parent.name not in changed
    }
    report: dict[str, object] = {
        "base": base,
        "changed_package_candidates": changed,
        "unselected_candidates": sorted(
            set(changed) - capabilities - ({POD} if include_pod else set())
        ),
        "manifest_candidates": manifest_candidates(root, set(changed)),
        "selected_packages": dict(sorted(versions.items())),
        "unchanged_capabilities": unchanged_capabilities,
        "selected_manifests": manifest_targets,
        "lock_projects": [str(path.relative_to(root)) for path in locks],
    }
    if apply:
        for path, content in paths.items():
            path.write_text(content)
        uv = os.environ.get("UV", "uv")
        env = {key: value for key, value in os.environ.items() if key != "VIRTUAL_ENV"}
        for directory in locks:
            subprocess.run([uv, "lock", "--quiet"], cwd=directory, env=env, check=True)
        verify_locks(locks, versions, expected_locks)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "apply"))
    parser.add_argument("--base", required=True, help="previous stable code/vX.Y.Z tag")
    parser.add_argument(
        "--capability",
        action="append",
        default=[],
        help="changed capability distribution",
    )
    parser.add_argument(
        "--manifest", action="append", default=[], help="affected capability.py path"
    )
    parser.add_argument(
        "--pod", action="store_true", help="also advance a changed fred-pod"
    )
    args = parser.parse_args()
    try:
        report = prepare(
            ROOT,
            args.base,
            set(args.capability),
            {Path(path) for path in args.manifest},
            args.pod,
            apply=args.command == "apply",
        )
        print(json.dumps(report, indent=2))
        return 0
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"Python release preparation: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
