#!/usr/bin/env python3
"""Scan Fred release images or fresh local builds with Trivy."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
MANIFEST = ROOT / ".github/docker-images.json"
TRIVY_IMAGE = "ghcr.io/aquasecurity/trivy:0.75.0"
REGISTRY = "ghcr.io/thalesgroup/fred-agent"
SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN")


def run(*args: str, cwd: Path = ROOT, capture: bool = False) -> str:
    print("+", " ".join(args), file=sys.stderr)
    result = subprocess.run(args, cwd=cwd, check=True, text=True, capture_output=capture)
    return result.stdout.strip() if capture else ""


def git(*args: str) -> str:
    return run("git", *args, capture=True)


def inspect_image(ref: str) -> dict:
    image = json.loads(run("docker", "image", "inspect", ref, capture=True))[0]
    repository = ref.split(":")[0]
    digest = next(
        (value for value in image.get("RepoDigests", []) if value.startswith(repository + "@")),
        None,
    )
    labels = (image.get("Config") or {}).get("Labels") or {}
    return {
        "ref": ref,
        "digest": digest or image["Id"],
        "revision": labels.get("org.opencontainers.image.revision"),
    }


def build_image(image: dict, head: str, use_cache: bool) -> dict:
    ref = f"fred-trivy-assessment/{image['name']}:{head[:12]}"
    command = ["docker", "build", "--pull"]
    if not use_cache:
        command.append("--no-cache")
    command += ["--file", image["dockerfile"], "--tag", ref]
    for build_arg in image.get("build_args", "").splitlines():
        if build_arg.strip():
            command += ["--build-arg", build_arg.strip()]
    command.append(image["context"])
    run(*command)
    return inspect_image(ref)


def trivy_run(
    output: Path, *args: str, mount_repo: bool = False, mount_docker: bool = False
) -> None:
    command = ["docker", "run", "--rm", "--user", f"{os.getuid()}:{os.getgid()}"]
    if mount_docker:
        socket = Path("/var/run/docker.sock")
        command += [
            "--group-add",
            str(socket.stat().st_gid),
            "--volume",
            f"{socket}:{socket}",
        ]
    if mount_repo:
        command += ["--volume", f"{ROOT}:/workspace:ro"]
    command += [
        "--volume",
        f"{output}:/reports",
        "--volume",
        f"{output / 'cache'}:/cache",
        TRIVY_IMAGE,
        *args,
    ]
    run(*command)


def scan_image(image: dict, output: Path) -> Path:
    report = output / f"{image['name']}.json"
    trivy_run(
        output,
        "image",
        "--image-src",
        "docker",
        "--cache-dir",
        "/cache",
        "--scanners",
        "vuln",
        "--pkg-types",
        "os,library",
        "--severity",
        ",".join(SEVERITIES),
        "--list-all-pkgs",
        "--format",
        "json",
        "--output",
        f"/reports/{report.name}",
        "--exit-code",
        "0",
        image["ref"],
        mount_docker=True,
    )
    return report


def scan_frontend_lockfile(output: Path) -> Path:
    report = output / "frontend-dependencies.json"
    trivy_run(
        output,
        "fs",
        "--cache-dir",
        "/cache",
        "--config",
        "/workspace/.github/trivy-frontend.yaml",
        "--scanners",
        "vuln",
        "--pkg-types",
        "library",
        "--severity",
        ",".join(SEVERITIES),
        "--list-all-pkgs",
        "--format",
        "json",
        "--output",
        f"/reports/{report.name}",
        "--exit-code",
        "0",
        "/workspace/apps/frontend",
        mount_repo=True,
    )
    return report


def findings(report: Path, artifact_type: str) -> tuple[list[dict], int]:
    data = json.loads(report.read_text())
    if data.get("ArtifactType") != artifact_type or not data.get("Results"):
        raise ValueError(f"Trivy did not inventory {report.name} as {artifact_type}")
    if artifact_type == "filesystem" and not any(
        str(result.get("Target", "")).endswith("package-lock.json") and result.get("Packages")
        for result in data["Results"]
    ):
        raise ValueError("Trivy did not inventory the frontend package-lock.json")
    rows = [
        {**item, "Target": result.get("Target", "-")}
        for result in data["Results"]
        for item in result.get("Vulnerabilities") or []
    ]
    packages = sum(len(result.get("Packages") or []) for result in data["Results"])
    if artifact_type == "container_image" and not packages:
        raise ValueError(f"Trivy did not inventory packages in {report.name}")
    return rows, packages


def cell(value: object) -> str:
    return str(value or "-").replace("|", "\\|").replace("\n", " ")


def render_report(mode: str, head: str, images: list[dict], output: Path) -> str:
    lines = [
        "# Fred Trivy image assessment",
        "",
        f"- Mode: `{mode}`",
        f"- Scanned at: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"- Checkout HEAD: `{head}`",
        f"- Scanner image: `{TRIVY_IMAGE}`",
        "- Counts are findings per scan target, not unique CVE IDs.",
    ]
    if mode == "swift-dev":
        lines.append(
            "- These are the last published `swift-dev` images. "
            "Release tags rebuild images from the release commit."
        )
    else:
        lines.append("- Images were built from the current working tree with fresh base images.")
    lines += [
        "",
        "| Image | Pulled digest or local ID | CRITICAL | HIGH | MEDIUM | LOW | UNKNOWN |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    all_rows: list[tuple[str, dict]] = []
    for image in images:
        rows, packages = findings(output / f"{image['name']}.json", "container_image")
        image["findings"] = rows
        image["packages"] = packages
        all_rows.extend((image["name"], row) for row in rows)
        counts = [
            str(sum((row.get("Severity") or "UNKNOWN") == severity for row in rows))
            for severity in SEVERITIES
        ]
        lines.append(
            f"| {image['name']} | `{cell(image['digest'])}` | " + " | ".join(counts) + " |"
        )
    frontend_rows, frontend_packages = findings(output / "frontend-dependencies.json", "filesystem")
    all_rows.extend(("frontend dependencies", row) for row in frontend_rows)
    counts = [
        str(sum((row.get("Severity") or "UNKNOWN") == severity for row in frontend_rows))
        for severity in SEVERITIES
    ]
    lines.append("| frontend dependencies | checkout lockfile | " + " | ".join(counts) + " |")
    lines += [
        "",
        "Package inventory entries: "
        + ", ".join(f"{image['name']} {image['packages']}" for image in images)
        + f", frontend dependencies {frontend_packages}.",
        "",
        "## Fix availability reported by Trivy",
        "",
        "A nonempty `FixedVersion` means Trivy lists a fixed package version. "
        "An empty value means no fixed version is listed; it does not prove "
        "remediation is impossible.",
        "",
        "| Severity | Findings | Fixed version listed | No fixed version listed |",
        "| --- | ---: | ---: | ---: |",
    ]
    for severity in SEVERITIES:
        group = [row for _, row in all_rows if (row.get("Severity") or "UNKNOWN") == severity]
        fixed = sum(bool(row.get("FixedVersion")) for row in group)
        lines.append(f"| {severity} | {len(group)} | {fixed} | {len(group) - fixed} |")
    lines += [
        "",
        "## Critical findings",
        "",
        "| Target | ID | Package | Installed | Fixed version | Scanner target |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    critical = [(name, row) for name, row in all_rows if row.get("Severity") == "CRITICAL"]
    if not critical:
        lines.append("| None | - | - | - | - | - |")
    for name, row in critical:
        lines.append(
            "| " + " | ".join(
                cell(value)
                for value in (
                    name,
                    row.get("VulnerabilityID"),
                    row.get("PkgName"),
                    row.get("InstalledVersion"),
                    row.get("FixedVersion") or "No fixed version listed",
                    row.get("Target"),
                )
            ) + " |"
        )
    lines += ["", "Raw JSON reports are stored beside this summary.", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("swift-dev", "build"))
    parser.add_argument(
        "--output-dir", type=Path, help="New directory for the Markdown and JSON reports"
    )
    parser.add_argument(
        "--use-cache", action="store_true", help="Reuse Docker build cache in build mode"
    )
    args = parser.parse_args()
    if args.use_cache and args.mode != "build":
        parser.error("--use-cache applies only to build mode")

    output = (
        args.output_dir.resolve()
        if args.output_dir
        else Path(tempfile.mkdtemp(prefix="fred-trivy-"))
    )
    if args.output_dir:
        output.mkdir(parents=True, exist_ok=False)
    (output / "cache").mkdir()
    print(f"Reports: {output}", file=sys.stderr)

    head = git("rev-parse", "HEAD")
    if args.mode == "swift-dev":
        if git("symbolic-ref", "--short", "HEAD") != "swift":
            raise ValueError("swift-dev mode requires a swift checkout")
        if git("rev-parse", "origin/swift") != head:
            raise ValueError(
                "local swift differs from origin/swift; fetch and reconcile before auditing"
            )

    manifest = json.loads(MANIFEST.read_text())
    candidates = [image for image in manifest["images"] if image["publish"]]
    if not candidates:
        raise ValueError("no publishable images in .github/docker-images.json")
    images = []
    for image in candidates:
        if args.mode == "swift-dev":
            ref = f"{REGISTRY}/{image['name']}:swift-dev"
            run("docker", "pull", ref)
            inspected = inspect_image(ref)
            if inspected["revision"] != head:
                raise ValueError(
                    f"{ref} contains revision {inspected['revision']!r}, expected {head}; "
                    "wait for the swift image publish workflow"
                )
        else:
            inspected = build_image(image, head, args.use_cache)
        inspected["name"] = image["name"]
        images.append(inspected)

    for image in images:
        scan_image(image, output)
    scan_frontend_lockfile(output)
    report = render_report(args.mode, head, images, output)
    (output / "report.md").write_text(report)
    print(report)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (subprocess.CalledProcessError, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Trivy assessment failed: {error}", file=sys.stderr)
        sys.exit(1)
