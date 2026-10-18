"""Assert and record the installed PDF profile, including package files and licenses.

Run with the target environment's Python. The inventory is emitted to stdout so
CI can bind it to an image digest and retain it alongside the image SBOM.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
import re

from packaging.requirements import Requirement

FAMILY = {"pymupdf", "pymupdf4llm", "pymupdf-layout"}
MODULES = ("fitz", "pymupdf", "pymupdf4llm")


def inventory() -> dict:
    packages = {}
    for dist in importlib.metadata.distributions():
        name = re.sub(r"[-_.]+", "-", dist.metadata["Name"]).lower()
        packages[name] = {
            "version": dist.version,
            "license": dist.metadata.get("License-Expression")
            or dist.metadata.get("License"),
            "requires": dist.requires or [],
            "files": [str(file) for file in dist.files or []],
        }
    return packages


def runtime_closure(packages: dict, extras: tuple[str, ...] = ()) -> set[str]:
    """Follow installed metadata's active dependency edges, including extra markers."""
    pending = [("knowledge-flow-backend", extras)]
    seen = set()
    reached = set()
    while pending:
        name, active = pending.pop()
        key = (name, tuple(sorted(active)))
        if key in seen:
            continue
        seen.add(key)
        reached.add(name)
        for value in packages.get(name, {}).get("requires", []):
            requirement = Requirement(value)
            if requirement.marker and not any(
                requirement.marker.evaluate({"extra": extra}) for extra in ("", *active)
            ):
                continue
            child = re.sub(r"[-_.]+", "-", requirement.name).lower()
            pending.append((child, tuple(requirement.extras)))
    return reached


def check(packages: dict, enabled: bool) -> None:
    reachable = FAMILY & runtime_closure(packages, ("pymupdf",) if enabled else ())
    if reachable != (FAMILY if enabled else set()):
        raise RuntimeError(
            f"Unexpected PyMuPDF dependency reachability: {sorted(reachable)}"
        )
    present = FAMILY & packages.keys()
    if present != (FAMILY if enabled else set()):
        raise RuntimeError(
            f"Unexpected PyMuPDF inventory: {sorted(present)} (enabled={enabled})"
        )
    if not enabled:
        unexpected = [
            module for module in MODULES if importlib.util.find_spec(module) is not None
        ]
        if unexpected:
            raise RuntimeError(f"Untracked PyMuPDF modules remain: {unexpected}")
    for name in ("pypdf", "pypdfium2", "docling", "markitdown"):
        if name not in packages:
            raise RuntimeError(f"Missing default PDF dependency: {name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pymupdf", action="store_true")
    args = parser.parse_args()
    packages = inventory()
    check(packages, args.pymupdf)
    print(json.dumps(packages, indent=2))
