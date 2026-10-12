#!/usr/bin/env python3
"""Give Fred's PyPI packages one version: `make libs-version VERSION=x.y.z`.

Sets `[project].version` of every package named on the command line, rewrites
each `>=` floor one of them puts on another to that version, then relocks every
uv project under libs/ and apps/ that resolves one of them. Nothing else.

The lockfiles are written by the `uv` on PATH, or by `$UV` when set.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION = re.compile(r"\d+\.\d+\.\d+")
PROJECT_TABLE = re.compile(r"^\[project\]\n(.*?)(?=^\[|\Z)", re.M | re.S)
PROJECT_VERSION = re.compile(r'^version = "[^"]*"$', re.M)


def package_name(package_dir: Path) -> str:
    """The distribution name a package publishes under."""
    data = tomllib.loads((package_dir / "pyproject.toml").read_text())
    return data["project"]["name"]


def rewrite(text: str, names: list[str], version: str) -> str:
    """One pyproject.toml with its version and its floors on `names` set."""
    table = PROJECT_TABLE.search(text)
    if table is None or not PROJECT_VERSION.search(table.group(1)):
        raise ValueError("no `version = \"...\"` line in [project]")
    body = PROJECT_VERSION.sub(f'version = "{version}"', table.group(1), count=1)
    text = text[: table.start(1)] + body + text[table.end(1) :]

    # A requirement on one of the packages: "name", "name[extra]", then its
    # specifier. Only a lone `>=` floor is ours to move; anything else would
    # mean someone decided otherwise, and is reported rather than overwritten.
    alternatives = "|".join(re.escape(name) for name in names)
    requirement = re.compile(rf'"({alternatives})(\[[^\]"]*\])?([<>=!~][^"]*)"')

    def floor(match: re.Match[str]) -> str:
        name, extras, specifier = match.group(1), match.group(2) or "", match.group(3)
        if not re.fullmatch(r">=\s*[^,;\s]+", specifier):
            raise ValueError(f"{name}{extras}{specifier}: only a single `>=` floor is rewritten")
        return f'"{name}{extras}>={version}"'

    return requirement.sub(floor, text)


def lock_dirs(names: list[str]) -> list[Path]:
    """Every uv project under libs/ and apps/ whose lock resolves a package."""
    locks = sorted([*(ROOT / "libs").rglob("uv.lock"), *(ROOT / "apps").rglob("uv.lock")])
    wanted = [f'name = "{name}"' for name in names]
    return [
        lock.parent
        for lock in locks
        if not {"target", ".venv", "node_modules"} & set(lock.relative_to(ROOT).parts)
        and any(line in lock.read_text() for line in wanted)
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--version", required=True, help="x.y.z")
    parser.add_argument("packages", nargs="+", help="package directories, relative to the repository root")
    args = parser.parse_args()

    if not VERSION.fullmatch(args.version):
        parser.error(f"VERSION must be x.y.z, got {args.version!r}")

    package_dirs = [ROOT / package for package in args.packages]
    names = [package_name(package_dir) for package_dir in package_dirs]

    for package_dir in package_dirs:
        pyproject = package_dir / "pyproject.toml"
        try:
            pyproject.write_text(rewrite(pyproject.read_text(), names, args.version))
        except ValueError as error:
            print(f"{pyproject.relative_to(ROOT)}: {error}", file=sys.stderr)
            return 1
        print(f"{package_name(package_dir)} {args.version}")

    uv = os.environ.get("UV", "uv")
    env = {key: value for key, value in os.environ.items() if key != "VIRTUAL_ENV"}
    for project in lock_dirs(names):
        print(f"Relocking {project.relative_to(ROOT)}")
        subprocess.run([uv, "lock", "--quiet"], cwd=project, env=env, check=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
