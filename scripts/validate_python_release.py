#!/usr/bin/env python3
"""Validate independently versioned FRED PyPI artifacts before any upload."""

from __future__ import annotations

import argparse
import email.parser
import io
import json
import re
import sys
import tarfile
import tomllib
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

NAME = re.compile(r"^([A-Za-z0-9_.-]+)(?:\[[^]]+\])?(.*)$")
STABLE = re.compile(r"\d+\.\d+\.\d+")
PYPI = "https://pypi.org/pypi"
# A rebuild of unchanged sources still differs in these wheel entries: WHEEL
# stamps the setuptools version and RECORD hashes WHEEL.
REBUILT = ("WHEEL", "RECORD")


def canonical(name: str) -> str:
    """Return the normalized distribution name used for comparisons."""
    return re.sub(r"[-_.]+", "-", name).lower()


def project(package_dir: Path) -> dict[str, object]:
    """Load one package's project table."""
    return tomllib.loads((package_dir / "pyproject.toml").read_text())["project"]


def requirements(data: dict[str, object]) -> list[str]:
    """Return every dependency that is published in wheel metadata."""
    result = list(data.get("dependencies", []))
    for values in dict(data.get("optional-dependencies", {})).values():
        result.extend(values)
    return result


def check_floors(
    requirements_to_check: list[str],
    *,
    owner: str,
    versions: dict[str, str],
    prepared: set[str],
) -> list[str]:
    """Check internal floors against the package map and selected increments."""
    errors: list[str] = []
    for requirement in requirements_to_check:
        match = NAME.match(requirement)
        if match is None:
            continue
        dependency = canonical(match.group(1))
        if dependency not in versions or dependency == canonical(owner):
            continue
        specifier = match.group(2).split(";", 1)[0].replace(" ", "")
        floor = re.fullmatch(r">=(\d+\.\d+\.\d+)", specifier)
        if floor is None:
            errors.append(
                f"{owner}: {requirement!r} must use a single stable >=X.Y.Z floor"
            )
            continue
        current = tuple(int(part) for part in versions[dependency].split("."))
        minimum = tuple(int(part) for part in floor[1].split("."))
        if minimum > current:
            errors.append(
                f"{owner}: {requirement!r} exceeds {dependency} {versions[dependency]}"
            )
        elif (
            owner in prepared
            and dependency in prepared
            and floor[1] != versions[dependency]
        ):
            errors.append(
                f"{owner}: {requirement!r} must use the prepared {dependency} "
                f"floor >={versions[dependency]}"
            )
    return errors


def internal_requirements(
    values: list[str], *, owner: str, internal_names: set[str]
) -> set[tuple[str, str, str]]:
    """Normalize internal metadata requirements across project and built archives."""
    result: set[tuple[str, str, str]] = set()
    for value in values:
        match = NAME.match(value)
        if match is None:
            continue
        name = canonical(match.group(1))
        if name not in internal_names or name == canonical(owner):
            continue
        extras_match = re.match(r"\[([^]]+)\]", value[len(match.group(1)) :])
        extras = extras_match[1] if extras_match else ""
        specifier = match.group(2).split(";", 1)[0].replace(" ", "")
        result.add((name, extras, specifier))
    return result


def metadata(text: str) -> email.message.Message:
    """Parse Python core metadata without third-party dependencies."""
    return email.parser.Parser().parsestr(text)


def validate_artifacts(
    package_dir: Path,
    *,
    name: str,
    version: str,
    versions: dict[str, str],
    prepared: set[str],
    declared: list[str],
) -> list[str]:
    """Validate the exact wheel and sdist that the publish target will upload."""
    errors: list[str] = []
    dist = package_dir / "target" / "dist"
    stem = name.replace("-", "_")
    wheel = dist / f"{stem}-{version}-py3-none-any.whl"
    sdist = dist / f"{stem}-{version}.tar.gz"
    expected = {wheel, sdist}
    # uv creates a harmless .gitignore in dist; the publish glob excludes dotfiles.
    actual = (
        {path for path in dist.iterdir() if not path.name.startswith(".")}
        if dist.is_dir()
        else set()
    )
    if actual != expected:
        rendered = ", ".join(sorted(path.name for path in actual)) or "none"
        errors.append(
            f"{name}: target/dist must contain only the expected wheel and sdist; found {rendered}"
        )
        return errors

    with zipfile.ZipFile(wheel) as archive:
        candidates = [
            entry
            for entry in archive.namelist()
            if entry.endswith(".dist-info/METADATA")
        ]
        if len(candidates) != 1:
            errors.append(f"{name}: wheel must contain exactly one METADATA file")
        else:
            wheel_metadata = metadata(archive.read(candidates[0]).decode())
            if canonical(wheel_metadata["Name"]) != canonical(name):
                errors.append(f"{name}: wheel metadata has the wrong project name")
            if wheel_metadata["Version"] != version:
                errors.append(
                    f"{name}: wheel metadata has version {wheel_metadata['Version']}"
                )
            actual = internal_requirements(
                wheel_metadata.get_all("Requires-Dist", []),
                owner=name,
                internal_names=set(versions),
            )
            expected_requirements = internal_requirements(
                declared, owner=name, internal_names=set(versions)
            )
            if actual != expected_requirements:
                errors.append(
                    f"{name}: wheel internal requirements differ from pyproject.toml: {actual}"
                )
            errors.extend(
                check_floors(
                    wheel_metadata.get_all("Requires-Dist", []),
                    owner=name,
                    versions=versions,
                    prepared=prepared,
                )
            )

    with tarfile.open(sdist, "r:gz") as archive:
        candidates = [
            member
            for member in archive.getmembers()
            if member.name.endswith("/PKG-INFO") and member.name.count("/") == 1
        ]
        if len(candidates) != 1:
            errors.append(f"{name}: sdist must contain exactly one PKG-INFO file")
        else:
            extracted = archive.extractfile(candidates[0])
            if extracted is None:
                errors.append(f"{name}: cannot read sdist PKG-INFO")
            else:
                sdist_metadata = metadata(extracted.read().decode())
                if canonical(sdist_metadata["Name"]) != canonical(name):
                    errors.append(f"{name}: sdist metadata has the wrong project name")
                if sdist_metadata["Version"] != version:
                    errors.append(
                        f"{name}: sdist metadata has version {sdist_metadata['Version']}"
                    )
                actual = internal_requirements(
                    sdist_metadata.get_all("Requires-Dist", []),
                    owner=name,
                    internal_names=set(versions),
                )
                expected_requirements = internal_requirements(
                    declared, owner=name, internal_names=set(versions)
                )
                if actual != expected_requirements:
                    errors.append(
                        f"{name}: sdist internal requirements differ from pyproject.toml: {actual}"
                    )
                errors.extend(
                    check_floors(
                        sdist_metadata.get_all("Requires-Dist", []),
                        owner=name,
                        versions=versions,
                        prepared=prepared,
                    )
                )
    return errors


def version_key(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))


def fetch(url: str) -> bytes | None:
    """Return a PyPI response body, None when PyPI does not have it.

    Any answer other than 200 or 404 raises: the release stops rather than guess.
    """
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise


def wheel_entries(data: bytes) -> dict[str, bytes]:
    """Return a wheel's entries, without the ones every rebuild changes."""
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {
            entry: archive.read(entry)
            for entry in archive.namelist()
            if not any(entry.endswith(f".dist-info/{name}") for name in REBUILT)
        }


def compare_with_pypi(
    package_dir: Path, name: str, version: str
) -> tuple[bool, list[str]]:
    """Decide whether one built package is to upload, against PyPI's releases.

    A version above PyPI's latest is to upload, whatever releases were skipped.
    PyPI's latest version is to skip, provided the built wheel is the published
    one: a change shipped under an unchanged version is a forgotten bump.
    """
    if STABLE.fullmatch(version) is None:
        return False, [f"{name}: {version} is not a stable X.Y.Z version"]
    body = fetch(f"{PYPI}/{name}/json")
    if body is None:
        return True, []
    releases: dict[str, list[dict[str, str]]] = json.loads(body)["releases"]
    latest = max(
        (value for value in releases if STABLE.fullmatch(value)),
        key=version_key,
        default=None,
    )
    if version not in releases:
        if latest is not None and version_key(version) < version_key(latest):
            return False, [f"{name}: {version} is below {latest}, the latest on PyPI"]
        return True, []
    if version != latest:
        return False, [f"{name}: {version} is on PyPI but {latest} is the latest"]
    stem = name.replace("-", "_")
    wheel = package_dir / "target" / "dist" / f"{stem}-{version}-py3-none-any.whl"
    published = next(
        (
            file["url"]
            for file in releases[version]
            if file["packagetype"] == "bdist_wheel"
        ),
        None,
    )
    if not wheel.is_file():
        return False, [f"{name}: {wheel} is missing; build before comparing"]
    if published is None or (remote := fetch(published)) is None:
        return False, [f"{name}: PyPI has no wheel for {version} to compare with"]
    local, remote_entries = wheel_entries(wheel.read_bytes()), wheel_entries(remote)
    changed = sorted(
        entry
        for entry in local.keys() | remote_entries.keys()
        if local.get(entry) != remote_entries.get(entry)
    )
    if changed:
        shown = ", ".join(changed[:5]) + (", ..." if len(changed) > 5 else "")
        return False, [
            f"{name}: differs from {version} on PyPI but its version was not "
            f"raised ({shown})"
        ]
    return False, []


def release_plan(package_dirs: list[Path]) -> tuple[list[Path], list[str]]:
    """Return the packages to upload, in order, and what forbids the release."""
    pending: list[Path] = []
    errors: list[str] = []
    for package_dir in package_dirs:
        data = project(package_dir)
        name, version = canonical(str(data["name"])), str(data["version"])
        upload, package_errors = compare_with_pypi(package_dir, name, version)
        errors.extend(package_errors)
        if upload:
            pending.append(package_dir)
        state = "blocked" if package_errors else "to publish" if upload else "on PyPI"
        print(f"{name} {version}: {state}", file=sys.stderr)
    return pending, errors


def validate(
    package_dirs: list[Path],
    *,
    prepared: set[str] | None = None,
    pending: set[Path] | None = None,
) -> list[str]:
    """Validate the complete package map and artifacts selected for publication.

    ``prepared`` names the packages getting a new version: their internal floors
    must name the new versions of the other prepared packages.
    """
    projects = [(package_dir, project(package_dir)) for package_dir in package_dirs]
    versions = {
        canonical(str(data["name"])): str(data["version"]) for _, data in projects
    }
    if len(versions) != len(projects):
        return ["Duplicate Python package names in release inventory"]
    prepared = prepared or set()
    errors: list[str] = []
    if pending is not None and (unknown := (pending - set(package_dirs))):
        errors.append(
            f"Unknown pending packages: {', '.join(str(path) for path in sorted(unknown))}"
        )
    for package_dir, data in projects:
        name = canonical(str(data["name"]))
        declared = requirements(data)
        errors.extend(
            check_floors(
                declared,
                owner=name,
                versions=versions,
                prepared=prepared,
            )
        )
        if pending is None or package_dir in pending:
            errors.extend(
                validate_artifacts(
                    package_dir,
                    name=name,
                    version=versions[name],
                    versions=versions,
                    prepared=prepared,
                    declared=declared,
                )
            )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pypi",
        action="store_true",
        help="compare the built packages with PyPI and print, one per line, "
        "the directories to upload in order",
    )
    parser.add_argument("packages", nargs="+", help="package directories")
    args = parser.parse_args()
    package_dirs = [Path(package).resolve() for package in args.packages]
    if not args.pypi:
        errors = validate(package_dirs)
    else:
        try:
            pending, errors = release_plan(package_dirs)
        except (OSError, ValueError, KeyError) as error:
            print(f"PyPI could not be compared: {error}; stopping.", file=sys.stderr)
            return 1
        errors += validate(
            package_dirs,
            prepared={canonical(str(project(path)["name"])) for path in pending},
            pending=set(pending),
        )
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    if args.pypi:
        for package_dir in pending:
            print(package_dir)
        if not pending:
            print("Nothing to publish: PyPI has every package.", file=sys.stderr)
        return 0
    print(f"Validated {len(package_dirs)} package manifest(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
