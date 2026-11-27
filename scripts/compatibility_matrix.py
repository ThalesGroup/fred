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

# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "jsonschema>=4.18,<5",
#   "pyyaml>=6.0",
# ]
# ///
"""Derive a Fred release's compatibility matrix from the client libraries it locks.

Nobody writes server versions by hand. The client versions come from each component's
lockfile (apps/*/uv.lock); deploy/compatibility/clients.yaml says which server versions
each client version supports, as its maintainers publish it. A service's range is what
every locked client of that service supports.

    check                       validate the table and that it covers every locked client
    build --version 3.18.0 ...  write the matrix of a release

See deploy/compatibility/README.md.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parent.parent
TABLE_DIR = Path("deploy/compatibility")
API_VERSION = "fred.dev/v1alpha1"
RANGE = re.compile(r">=([0-9]+(?:\.[0-9]+){0,2})(?: <([0-9]+(?:\.[0-9]+){0,2}))?")
LEADING_VERSION = re.compile(r"([0-9]+)(?:\.([0-9]+))?(?:\.([0-9]+))?")
RELEASE = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?")
ANY, UNKNOWN = "*", "unknown"

Version = tuple[int, int, int]


class CompatibilityError(ValueError):
    """The table, a lockfile or the derived matrix is wrong."""


@dataclass(frozen=True)
class Bounds:
    """A floor and an optional excluded cap."""

    floor: Version
    cap: Version | None

    def contains(self, version: Version) -> bool:
        return self.floor <= version and (self.cap is None or version < self.cap)

    def intersect(self, other: Bounds) -> Bounds | None:
        floor = max(self.floor, other.floor)
        caps = [cap for cap in (self.cap, other.cap) if cap is not None]
        cap = min(caps) if caps else None
        return None if cap is not None and floor >= cap else Bounds(floor, cap)

    def render(self) -> str:
        text = f">={_render(self.floor)}"
        return text if self.cap is None else f"{text} <{_render(self.cap)}"


def _render(version: Version) -> str:
    return ".".join(str(part) for part in version)


def _version(text: str) -> Version:
    """The numeric X.Y.Z prefix of a version; a pre/post-release suffix is ignored."""
    match = LEADING_VERSION.match(text)
    if match is None:
        raise CompatibilityError(f"cannot read version {text!r}")
    major, minor, patch = (int(part or 0) for part in match.groups())
    return major, minor, patch


def parse_range(text: str) -> Bounds:
    match = RANGE.fullmatch(text)
    if match is None:
        raise CompatibilityError(
            f"range {text!r} must read '>=FLOOR' or '>=FLOOR <CAP'"
        )
    bounds = Bounds(
        _version(match[1]), None if match[2] is None else _version(match[2])
    )
    if bounds.cap is not None and bounds.floor >= bounds.cap:
        raise CompatibilityError(f"range {text!r} is empty")
    return bounds


def _normalized(name: str) -> str:
    """A package name as lockfiles write it (PEP 503)."""
    return re.sub(r"[-_.]+", "-", name).lower()


def load_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise CompatibilityError(f"{path}: {exc}") from exc


def validate(root: Path, instance: Any, schema_name: str, origin: str) -> None:
    schemas = {
        path.name.removesuffix(".schema.json"): json.loads(
            path.read_text(encoding="utf-8")
        )
        for path in sorted((root / TABLE_DIR / "schemas").glob("*.schema.json"))
    }
    registry: Registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas.values()
    )
    validator = Draft202012Validator(schemas[schema_name], registry=registry)
    errors = sorted(
        validator.iter_errors(instance), key=lambda e: list(e.absolute_path)
    )
    if errors:
        details = "; ".join(
            f"[{'.'.join(str(p) for p in error.absolute_path) or '<root>'}] {error.message}"
            for error in errors
        )
        raise CompatibilityError(f"{origin}: {details}")


@dataclass(frozen=True)
class Rule:
    service: str
    client: str
    versions: Bounds
    server: Bounds | str
    source: str
    note: str | None


def load_table(root: Path) -> list[Rule]:
    path = root / TABLE_DIR / "clients.yaml"
    document = load_yaml(path)
    validate(root, document, "client-compatibility", str(path.relative_to(root)))
    rules: list[Rule] = []
    owner: dict[str, str] = {}
    for service, entries in document["services"].items():
        for entry in entries:
            ecosystem, _, name = entry["client"].partition("/")
            client = f"{ecosystem}/{_normalized(name)}"
            where = f"clients.yaml: {service}: {client}"
            if owner.setdefault(client, service) != service:
                raise CompatibilityError(
                    f"{where} is already a client of {owner[client]}"
                )
            server = entry["server"]
            try:
                rule = Rule(
                    service=service,
                    client=client,
                    versions=parse_range(entry["versions"]),
                    server=server if server in (ANY, UNKNOWN) else parse_range(server),
                    source=entry["source"],
                    note=entry.get("note"),
                )
            except CompatibilityError as exc:
                raise CompatibilityError(f"{where}: {exc}") from exc
            for other in rules:
                if other.client == client and other.versions.intersect(rule.versions):
                    raise CompatibilityError(
                        f"{where}: versions {entry['versions']} overlap "
                        f"{other.versions.render()}"
                    )
            rules.append(rule)
    return rules


def locked_packages(root: Path) -> dict[str, dict[str, set[str]]]:
    """{client: {version: components}} for every component lockfile (apps/*/uv.lock)."""
    locks = sorted((root / "apps").glob("*/uv.lock"))
    if not locks:
        raise CompatibilityError("no component lockfile under apps/*/uv.lock")
    packages: dict[str, dict[str, set[str]]] = {}
    for lock in locks:
        component = lock.parent.name
        for package in tomllib.loads(lock.read_text(encoding="utf-8")).get(
            "package", []
        ):
            if "version" not in package:
                continue
            client = f"pypi/{_normalized(package['name'])}"
            packages.setdefault(client, {}).setdefault(package["version"], set()).add(
                component
            )
    return packages


def _rule_for(rules: list[Rule], client: str, version: str) -> Rule:
    for rule in rules:
        if rule.client == client and rule.versions.contains(_version(version)):
            return rule
    raise CompatibilityError(
        f"{client} {version} is outside every rule of deploy/compatibility/clients.yaml: "
        "add the rule for this client version from its maintainers' compatibility statement"
    )


def _server_text(server: Bounds | str) -> str:
    return server if isinstance(server, str) else server.render()


def derive(root: Path) -> dict[str, Any]:
    """The matrix's services: each one's range and the locked clients that justify it."""
    rules = load_table(root)
    locked = locked_packages(root)
    services: dict[str, dict[str, Any]] = {}
    used: set[Rule] = set()
    for client in sorted({rule.client for rule in rules}):
        versions = locked.get(client, {})
        for version in sorted(versions, key=_version):
            rule = _rule_for(rules, client, version)
            components = versions[version]
            used.add(rule)
            entry = {
                "client": client,
                "version": version,
                "usedBy": sorted(components),
                "server": _server_text(rule.server),
                "source": rule.source,
            }
            if rule.note:
                entry["note"] = rule.note
            service = services.setdefault(rule.service, {"bounds": [], "clients": []})
            service["clients"].append(entry)
            service["bounds"].append(rule.server)
    dead = [
        f"{rule.client} {rule.versions.render()}" for rule in rules if rule not in used
    ]
    if dead:
        raise CompatibilityError(
            f"clients.yaml: no locked version matches {', '.join(dead)}; remove these rules"
        )
    return {name: _service(name, data) for name, data in sorted(services.items())}


def _service(name: str, data: dict[str, Any]) -> dict[str, Any]:
    """Intersect what every client supports; one unknown client leaves the service unknown."""
    known = [server for server in data["bounds"] if isinstance(server, Bounds)]
    if UNKNOWN in data["bounds"]:
        result: dict[str, Any] = {"support": UNKNOWN}
    elif known:
        bounds = known[0]
        for other in known[1:]:
            common = bounds.intersect(other)
            if common is None:
                raise CompatibilityError(
                    f"{name}: the locked clients support no common server version"
                )
            bounds = common
        result = {"support": "range", "min": _render(bounds.floor)}
        if bounds.cap is not None:
            result["below"] = _render(bounds.cap)
        result["range"] = bounds.render()
    else:
        result = {"support": "any"}
    return {**result, "clients": data["clients"]}


def build(root: Path, version: str, commit: str, repository: str) -> dict[str, Any]:
    if not RELEASE.fullmatch(version):
        raise CompatibilityError(f"version {version!r} must read X.Y.Z or X.Y.Z-pre")
    matrix = {
        "apiVersion": API_VERSION,
        "kind": "CompatibilityMatrix",
        "release": version,
        "source": {"repository": repository, "commit": commit},
        "services": derive(root),
    }
    validate(root, matrix, "compatibility-matrix", "compatibility matrix")
    return matrix


def dump(matrix: dict[str, Any], path: Path) -> None:
    path.write_text(
        "# Generated by scripts/compatibility_matrix.py; see deploy/compatibility/README.md.\n"
        + yaml.safe_dump(matrix, sort_keys=False),
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    commands = parser.add_subparsers(dest="command", required=True)
    _ = commands.add_parser("check", help="validate the table against the lockfiles")
    build_parser = commands.add_parser("build", help="write a release's matrix")
    _ = build_parser.add_argument("--version", required=True, help="without the v")
    _ = build_parser.add_argument("--commit", required=True)
    _ = build_parser.add_argument("--repository", required=True, help="owner/name")
    _ = build_parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            services = derive(ROOT)
            for name, service in services.items():
                print(f"{name:12} {service.get('range', service['support'])}")
        else:
            dump(build(ROOT, args.version, args.commit, args.repository), args.output)
    except CompatibilityError as exc:
        print(f"compatibility matrix: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
