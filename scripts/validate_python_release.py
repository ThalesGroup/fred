#!/usr/bin/env python3
"""Validate coordinated FRED PyPI artifacts before any upload."""

from __future__ import annotations

import argparse
import email.parser
import re
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path

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
    internal_names: set[str],
    version: str,
) -> list[str]:
    """Require every cross-distribution FRED dependency to use the release floor."""
    errors: list[str] = []
    for requirement in requirements_to_check:
        match = NAME.match(requirement)
        if match is None:
            continue
        dependency = canonical(match.group(1))
        if dependency not in internal_names or dependency == canonical(owner):
            continue
        specifier = match.group(2).split(";", 1)[0].replace(" ", "")
        if specifier != f">={version}":
            errors.append(
                f"{owner}: {requirement!r} must use the exact floor >={version}"
            )
    return errors


def metadata(text: str) -> email.message.Message:
    """Parse Python core metadata without third-party dependencies."""
    return email.parser.Parser().parsestr(text)


def validate_artifacts(
    package_dir: Path,
    *,
    name: str,
    version: str,
    internal_names: set[str],
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
            errors.extend(
                check_floors(
                    wheel_metadata.get_all("Requires-Dist", []),
                    owner=name,
                    internal_names=internal_names,
                    version=version,
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
                errors.extend(
                    check_floors(
                        sdist_metadata.get_all("Requires-Dist", []),
                        owner=name,
                        internal_names=internal_names,
                        version=version,
                    )
                )
    return errors


def validate(package_dirs: list[Path]) -> list[str]:
    """Validate one package or a complete coordinated release."""
    projects = [(package_dir, project(package_dir)) for package_dir in package_dirs]
    versions = {str(data["version"]) for _, data in projects}
    if len(versions) != 1:
        rendered = ", ".join(
            f"{data['name']}={data['version']}" for _, data in projects
        )
        return [f"coordinated packages do not have one version: {rendered}"]

    version = versions.pop()
    internal_names = {canonical(str(data["name"])) for _, data in projects}
    errors: list[str] = []
    for package_dir, data in projects:
        name = str(data["name"])
        errors.extend(
            check_floors(
                requirements(data),
                owner=name,
                internal_names=internal_names,
                version=version,
            )
        )
        errors.extend(
            validate_artifacts(
                package_dir,
                name=name,
                version=version,
                internal_names=internal_names,
            )
        )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packages", nargs="+", help="package directories")
    args = parser.parse_args()
    package_dirs = [Path(package).resolve() for package in args.packages]
    errors = validate(package_dirs)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    data = project(package_dirs[0])
    print(f"Validated {len(package_dirs)} package(s) at {data['version']}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
