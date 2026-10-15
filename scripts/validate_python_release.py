#!/usr/bin/env python3
"""Validate independently versioned FRED PyPI artifacts before any upload."""

from __future__ import annotations

import argparse
import email.parser
import re
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path

from libs_version import SHARED, baseline, candidates, patch_after, tagged_text

ROOT = Path(__file__).resolve().parent.parent
NAME = re.compile(r"^([A-Za-z0-9_.-]+)(?:\[[^]]+\])?(.*)$")


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


def prepared_from_base(
    projects: list[tuple[Path, dict[str, object]]], base: str
) -> tuple[set[str], list[str]]:
    baseline(ROOT, base)
    prepared: set[str] = set()
    errors: list[str] = []
    for package_dir, data in projects:
        name = canonical(str(data["name"]))
        previous_text = tagged_text(
            ROOT, base, (package_dir / "pyproject.toml").relative_to(ROOT)
        )
        if previous_text is None:
            prepared.add(name)
            continue
        previous = str(tomllib.loads(previous_text)["project"]["version"])
        current = str(data["version"])
        target = patch_after(previous)
        if name in SHARED and current != target:
            errors.append(
                f"{name}: expected one patch after {previous}, found {current}"
            )
        elif current == target:
            prepared.add(name)
        elif current != previous:
            errors.append(f"{name}: expected {previous} or {target}, found {current}")
    for name in candidates(ROOT, base):
        if name not in prepared:
            errors.append(
                f"{name}: changed since {base} but its package version was not prepared"
            )
    return prepared, errors


def validate(
    package_dirs: list[Path],
    *,
    base: str | None = None,
    pending: set[Path] | None = None,
) -> list[str]:
    """Validate the complete package map and artifacts selected for publication."""
    projects = [(package_dir, project(package_dir)) for package_dir in package_dirs]
    versions = {
        canonical(str(data["name"])): str(data["version"]) for _, data in projects
    }
    if len(versions) != len(projects):
        return ["Duplicate Python package names in release inventory"]
    prepared, errors = prepared_from_base(projects, base) if base else (set(), [])
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
    parser.add_argument("--base", help="previous stable code/vX.Y.Z tag")
    parser.add_argument(
        "--pending", nargs="*", help="only these package directories need artifacts"
    )
    parser.add_argument("packages", nargs="+", help="package directories")
    args = parser.parse_args()
    package_dirs = [Path(package).resolve() for package in args.packages]
    errors = validate(
        package_dirs,
        base=args.base,
        pending={Path(path).resolve() for path in args.pending}
        if args.pending is not None
        else None,
    )
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print(f"Validated {len(package_dirs)} package manifest(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
