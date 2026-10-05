#!/usr/bin/env python3
"""Build Fred's local k3d images and write ordinary Helm image values."""

import argparse
import json
import subprocess
from pathlib import Path


def build(root: Path, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    applications = {}
    images = []
    for app, consumers in {
        "fred-agents": ["fred-agents"],
        "knowledge-flow-backend": ["knowledge-flow-backend", "knowledge-flow-worker"],
        "control-plane-backend": ["control-plane-backend", "control-plane-worker"],
        "frontend": ["frontend"],
    }.items():
        make = ["make", "--no-print-directory", "-C", str(root / "apps" / app)]
        image = subprocess.check_output(
            [
                *make,
                "-s",
                "--eval",
                "print-image: ; @echo $(IMAGE_FULL)",
                "print-image",
            ],
            text=True,
        ).strip()
        if not image or len(image.split()) != 1 or ":" not in image.rsplit("/", 1)[-1]:
            raise ValueError(f"Invalid IMAGE_FULL for {app}")
        log = output / f"{app}.log"
        print(f"Build {app} (log: {log})", flush=True)
        with log.open("w") as stream:
            # Dependency downloads occasionally fail; retain the existing single retry.
            result = subprocess.run(
                [*make, "docker-build"], stdout=stream, stderr=subprocess.STDOUT
            )
            if result.returncode:
                print(f"Retry {app}; see {log}", flush=True)
                subprocess.run(
                    [*make, "docker-build"],
                    stdout=stream,
                    stderr=subprocess.STDOUT,
                    check=True,
                )
        digest = subprocess.check_output(
            ["docker", "image", "inspect", "--format", "{{.Id}}", image], text=True
        ).strip()
        if not digest.startswith("sha256:") or len(digest) != 71:
            raise ValueError(f"Invalid Docker image ID for {app}")
        repository = image.rsplit(":", 1)[0]
        tag = f"k3d-{digest[7:19]}"
        reference = f"{repository}:{tag}"
        subprocess.run(["docker", "tag", image, reference], check=True)
        images.append(reference)
        for consumer in consumers:
            applications[consumer] = {"image": {"repository": repository, "tag": tag}}
        print(f"Built {app}: {reference}", flush=True)
    # Publish only a complete build's outputs; JSON is also valid Helm values YAML.
    for name, content in {
        "images.json": json.dumps({"applications": applications}, indent=2) + "\n",
        "images.txt": "\n".join(images) + "\n",
    }.items():
        temporary = output / f"{name}.tmp"
        temporary.write_text(content)
        temporary.replace(output / name)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=root / ".cache/k3d")
    args = parser.parse_args()
    build(root, args.output.resolve())
