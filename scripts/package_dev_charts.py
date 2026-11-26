# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
# /// script
# dependencies = ["pyyaml>=6.0"]
# ///
"""Package development charts only from a complete, same-commit image build."""

import argparse
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def read_digests(directory: Path, revision: str) -> dict[str, str]:
    images = json.loads((ROOT / ".github/docker-images.json").read_text())["images"]
    expected = {image["name"] for image in images if image["publish"]}
    digests = {}
    for path in directory.glob("*.json"):
        image = json.loads(path.read_text())
        name, digest = image["name"], image["digest"]
        if image["revision"] != revision or not re.fullmatch(
            r"sha256:[a-f0-9]{64}", digest
        ):
            raise ValueError(f"Invalid digest or source revision in {path}")
        if name in digests:
            raise ValueError(f"Duplicate image: {name}")
        digests[name] = digest
    if digests.keys() != expected:
        raise ValueError(
            f"Incomplete image build: expected {sorted(expected)}, got {sorted(digests)}"
        )
    return digests


def package(directory: Path, revision: str, version: str, output: Path) -> None:
    if not re.fullmatch(r"5\.0\.0-dev\.[1-9][0-9]*\.[1-9][0-9]*", version):
        raise ValueError("Expected development version 5.0.0-dev.<run-id>.<attempt>")
    digests = read_digests(directory, revision)
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        for name in ("fred", "agent-pod", "knowledge-base"):
            chart = Path(temporary) / name
            shutil.copytree(ROOT / "deploy/charts" / name, chart)
            metadata_path = chart / "Chart.yaml"
            metadata = yaml.safe_load(metadata_path.read_text())
            metadata["version"] = version
            metadata.setdefault("annotations", {})[
                "org.opencontainers.image.revision"
            ] = revision
            if name == "fred":
                metadata["appVersion"] = "v5-dev"
                values_path = chart / "values.yaml"
                values = values_path.read_text()
                for application in yaml.safe_load(values)["applications"].values():
                    if "image" not in application:
                        continue
                    repository = application["image"]["repository"]
                    digest = digests[repository.rsplit("/", 1)[-1]]
                    # Preserve the comments operators read with `helm show values`.
                    pattern = rf'(      repository: {re.escape(repository)}\n      digest: )""'
                    values, count = re.subn(
                        pattern, lambda match: match[1] + json.dumps(digest), values
                    )
                    if count != 1:
                        raise ValueError(
                            f"Expected exactly one default image block for {repository}"
                        )
                values_path.write_text(values)
                # Also records the optional PyMuPDF variant, not selected by default.
                (chart / "files").mkdir(exist_ok=True)
                (chart / "files/image-digests.json").write_text(
                    json.dumps({"revision": revision, "images": digests}, indent=2)
                    + "\n"
                )
            metadata_path.write_text(yaml.safe_dump(metadata, sort_keys=False))
            if name == "fred":
                subprocess.run(["helm", "lint", str(chart)], check=True)
            subprocess.run(
                ["helm", "package", str(chart), "--destination", str(output)],
                check=True,
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--digests", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    package(args.digests, args.revision, args.version, args.output)
