# /// script
# dependencies = [
#   "pyyaml>=6.0",
# ]
# ///
"""Render the Fred chart and check the knowledge-flow ingestion deployment.

Extraction is routed to a Temporal queue derived from the document's processing
profile. The API derives that name when it submits, each worker derives it from
its own role when it polls, and the document's bytes travel between them through
shared content storage. A rendered deployment therefore only ingests if the API
and all four worker groups agree on the Temporal server, the namespace, the base
task queue, the content storage and where documents land — and if something
actually polls every queue. None of that is visible to `helm lint`.

Two of these agreements have different mechanisms, and the checks below keep them
apart:

- Between the four worker groups, the three extraction deployments inherit the
  common worker at render time. A YAML anchor could not do this: it is resolved
  when values.yaml is parsed, before Helm merges any -f values file.
- Between the API and the workers, nothing propagates. They are separate
  applications and an overlay has to configure both.

Usage:
    python check_chart_ingestion_workers.py <chart-dir>

Exit code: 0 if every check passes, 1 otherwise.
"""

import argparse
import copy
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

WORKER_GROUPS = {
    "knowledge-flow-worker": "common",
    "knowledge-flow-worker-extraction-fast": "extraction-fast",
    "knowledge-flow-worker-extraction-medium": "extraction-medium",
    "knowledge-flow-worker-extraction-rich": "extraction-rich",
}

# Deliberately unlike anything in values.yaml: a value that matched the default
# would pass whether it propagated or not.
OVERRIDES = {
    "host": "temporal.audit.svc:7999",
    "namespace": "audit-ns",
    "task_queue": "audit-ingestion",
    "bucket_name": "audit-bucket",
    "repository": "registry.example.test/kf",
    "tag": "9.9.9-audit",
}

_ENABLE = {"enabled": True, "deployment": {"enabled": True}}

ALL_GROUPS_OVERRIDDEN = {
    "applications": {
        "knowledge-flow-worker": {
            **_ENABLE,
            "image": {"repository": OVERRIDES["repository"], "tag": OVERRIDES["tag"]},
            "configuration": {
                "scheduler": {
                    "temporal": {
                        "host": OVERRIDES["host"],
                        "namespace": OVERRIDES["namespace"],
                        "task_queue": OVERRIDES["task_queue"],
                    }
                },
                "content_storage": {
                    "type": "minio",
                    "root_path": None,
                    "endpoint": "http://audit-minio:9000",
                    "access_key": "audit-admin",
                    "bucket_name": OVERRIDES["bucket_name"],
                    "secure": False,
                },
            },
        },
        **{name: dict(_ENABLE) for name in WORKER_GROUPS if name != "knowledge-flow-worker"},
    }
}

HISTORICAL_WORKER_ONLY = {"applications": {"knowledge-flow-worker": dict(_ENABLE)}}

# A whole ingestion deployment retuned away from the chart defaults: the API and
# the four worker groups. The API is a separate application and inherits nothing,
# so the overlay configures it explicitly — which is what a real environment's
# values file has to do.
API_GROUP = "knowledge-flow-backend"

FULL_DEPLOYMENT_OVERRIDES = {
    "host": "temporal.full.svc:7998",
    "namespace": "full-ns",
    "task_queue": "full-ingestion",
    "bucket_name": "full-content",
    "vector_index": "full-vector-index",
}

_SHARED_INGESTION_CONFIGURATION = {
    "scheduler": {
        "temporal": {
            "host": FULL_DEPLOYMENT_OVERRIDES["host"],
            "namespace": FULL_DEPLOYMENT_OVERRIDES["namespace"],
            "task_queue": FULL_DEPLOYMENT_OVERRIDES["task_queue"],
        }
    },
    "content_storage": {
        "type": "minio",
        "root_path": None,
        "endpoint": "http://full-minio:9000",
        "access_key": "full-admin",
        "bucket_name": FULL_DEPLOYMENT_OVERRIDES["bucket_name"],
        "secure": False,
    },
    "storage": {
        "vector_store": {
            "type": "opensearch",
            "index": FULL_DEPLOYMENT_OVERRIDES["vector_index"],
            "bulk_size": 1000,
        }
    },
}


def _shared_ingestion_configuration() -> dict:
    return copy.deepcopy(_SHARED_INGESTION_CONFIGURATION)


FULL_DEPLOYMENT = {
    "applications": {
        API_GROUP: {"configuration": _shared_ingestion_configuration()},
        "knowledge-flow-worker": {**_ENABLE, "configuration": _shared_ingestion_configuration()},
        **{name: dict(_ENABLE) for name in WORKER_GROUPS if name != "knowledge-flow-worker"},
    }
}

LOCAL_SINGLE_POD = {
    "applications": {
        "knowledge-flow-worker": {
            **_ENABLE,
            "configuration": {"scheduler": {"worker_roles": list(WORKER_GROUPS.values())}},
        }
    }
}


def _render(chart: Path, values: dict) -> tuple[int, str]:
    with tempfile.NamedTemporaryFile("w", suffix=".yaml") as handle:
        yaml.safe_dump(values, handle)
        handle.flush()
        result = subprocess.run(
            ["helm", "template", "fred", str(chart), "-f", handle.name],
            capture_output=True,
            text=True,
        )
    return result.returncode, result.stdout if result.returncode == 0 else result.stderr


_ABSENT = "<absent>"


def _dig(config: dict, path: tuple[str, ...]) -> object:
    """Follow a key path, reporting an absent key instead of raising: an
    application left on the chart defaults may not carry it at all."""
    node: object = config
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return _ABSENT
        node = node[key]
    return node


def _rendered_configs(rendered: str, wanted: set[str]) -> tuple[dict, dict]:
    """The `configuration.yaml` of each wanted application's ConfigMap, plus the
    image of its Deployment."""
    configs, images = {}, {}
    for doc in yaml.safe_load_all(rendered):
        if not doc:
            continue
        name = doc.get("metadata", {}).get("name", "")
        if doc.get("kind") == "ConfigMap" and name.endswith("-back"):
            app = name[: -len("-back")]
            if app in wanted:
                configs[app] = yaml.safe_load(doc["data"]["configuration.yaml"])
        elif doc.get("kind") == "Deployment" and name in wanted:
            images[name] = doc["spec"]["template"]["spec"]["containers"][0]["image"]
    return configs, images


def _check_overrides_propagate(chart: Path) -> list[str]:
    """Every worker group must pick up an override applied to the common worker
    alone. This covers the worker groups only — the API inherits nothing from
    them, which is what the whole-deployment check below is for."""
    code, rendered = _render(chart, ALL_GROUPS_OVERRIDDEN)
    if code != 0:
        return [f"render with overrides failed: {rendered.strip()}"]

    errors = []
    configs, images = _rendered_configs(rendered, set(WORKER_GROUPS))
    missing = set(WORKER_GROUPS) - set(configs)
    if missing:
        return [f"groups missing from the render: {', '.join(sorted(missing))}"]

    for group, role in WORKER_GROUPS.items():
        temporal = configs[group]["scheduler"]["temporal"]
        storage = configs[group]["content_storage"]
        for key in ("host", "namespace", "task_queue"):
            if temporal[key] != OVERRIDES[key]:
                errors.append(f"{group}: scheduler.temporal.{key} is {temporal[key]!r}, expected the override {OVERRIDES[key]!r}")
        if storage.get("bucket_name") != OVERRIDES["bucket_name"]:
            errors.append(f"{group}: content_storage.bucket_name is {storage.get('bucket_name')!r}, expected the override {OVERRIDES['bucket_name']!r}")
        expected_image = f"{OVERRIDES['repository']}:{OVERRIDES['tag']}"
        if images.get(group) != expected_image:
            errors.append(f"{group}: image is {images.get(group)!r}, expected the override {expected_image!r}")
        if configs[group]["scheduler"]["worker_roles"] != [role]:
            errors.append(f"{group}: worker_roles is {configs[group]['scheduler']['worker_roles']!r}, expected [{role!r}]")

    rich = configs["knowledge-flow-worker-extraction-rich"]["scheduler"]["temporal"]
    if rich["ingestion_max_concurrent_activities"] != 1:
        errors.append(f"the rich group runs {rich['ingestion_max_concurrent_activities']} extractions per pod, expected 1")

    return errors


def _check_api_and_workers_agree(chart: Path) -> list[str]:
    """A whole ingestion deployment, API included, retuned off the chart defaults.

    The API derives the extraction queue names from its own base task queue when
    it submits, and saves the document into its own content storage before any
    worker reads it. If it disagrees with the workers on either, submissions land
    on queues nobody polls or extraction cannot find its input — so the render has
    to show one value across all five applications.
    """
    code, rendered = _render(chart, FULL_DEPLOYMENT)
    if code != 0:
        return [f"whole-deployment render failed: {rendered.strip()}"]

    applications = {API_GROUP, *WORKER_GROUPS}
    configs, _ = _rendered_configs(rendered, applications)
    missing = applications - set(configs)
    if missing:
        return [f"applications missing from the render: {', '.join(sorted(missing))}"]

    errors = []
    # What every application must agree on. An application left on the chart
    # defaults may not carry the key at all — a local content storage has no
    # bucket — so this reports the divergence rather than raising on it.
    shared = {
        ("scheduler", "temporal", "host"): FULL_DEPLOYMENT_OVERRIDES["host"],
        ("scheduler", "temporal", "namespace"): FULL_DEPLOYMENT_OVERRIDES["namespace"],
        ("scheduler", "temporal", "task_queue"): FULL_DEPLOYMENT_OVERRIDES["task_queue"],
        ("content_storage", "bucket_name"): FULL_DEPLOYMENT_OVERRIDES["bucket_name"],
        ("storage", "vector_store", "index"): FULL_DEPLOYMENT_OVERRIDES["vector_index"],
    }
    for path, expected in shared.items():
        actual = {app: _dig(configs[app], path) for app in sorted(applications)}
        disagreeing = {app: value for app, value in actual.items() if value != expected}
        if disagreeing:
            errors.append(f"{'.'.join(path)}: expected {expected!r} everywhere, got {disagreeing!r}")

    # Agreeing on the shared settings must not have flattened what each group is for.
    for group, role in WORKER_GROUPS.items():
        roles = configs[group]["scheduler"]["worker_roles"]
        if roles != [role]:
            errors.append(f"{group}: worker_roles is {roles!r}, expected [{role!r}]")
    concurrencies = {group: configs[group]["scheduler"]["temporal"]["ingestion_max_concurrent_activities"] for group in WORKER_GROUPS}
    expected_concurrencies = {
        "knowledge-flow-worker": 3,
        "knowledge-flow-worker-extraction-fast": 4,
        "knowledge-flow-worker-extraction-medium": 2,
        "knowledge-flow-worker-extraction-rich": 1,
    }
    if concurrencies != expected_concurrencies:
        errors.append(f"per-group activity concurrency is {concurrencies!r}, expected {expected_concurrencies!r}")

    return errors


def _check_unserved_role_is_refused(chart: Path) -> list[str]:
    """Enabling only the historical worker must fail, not quietly leave the three
    extraction queues without a consumer."""
    code, output = _render(chart, HISTORICAL_WORKER_ONLY)
    if code == 0:
        return ["enabling only knowledge-flow-worker rendered successfully; the three extraction queues would have no consumer"]
    if "extraction-rich" not in output:
        return [f"the refusal does not name the unserved roles: {output.strip()}"]
    return []


def _check_single_pod_serves_every_role(chart: Path) -> list[str]:
    """One process taking all four roles is how a developer's cluster runs."""
    code, output = _render(chart, LOCAL_SINGLE_POD)
    if code != 0:
        return [f"a single worker serving all four roles was refused: {output.strip()}"]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("chart", type=Path, help="Path to the Fred chart directory")
    args = parser.parse_args()

    checks = {
        "overrides reach every worker group": _check_overrides_propagate,
        "the API and the four worker groups agree": _check_api_and_workers_agree,
        "an unserved extraction role is refused": _check_unserved_role_is_refused,
        "one process may serve every role": _check_single_pod_serves_every_role,
    }

    failed = False
    for label, check in checks.items():
        errors = check(args.chart)
        if errors:
            failed = True
            print(f"FAIL  {label}")
            for error in errors:
                print(f"        {error}")
        else:
            print(f"OK    {label}")

    if failed:
        print("\nIngestion worker chart checks failed.")
        return 1
    print("\nIngestion worker chart checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
