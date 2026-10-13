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
# dependencies = []
# ///
"""Generate values.schema.json for the agent-pod and knowledge-base charts.

Each chart's `configuration` is the pod's configuration file, so its schema is the
library model's (AgentPodConfig, the Knowledge Base PodConfiguration), inlined
from the schemas generate_config_schema.py writes. The chart-level keys reuse
generate_chart_schema.py's Kubernetes primitives.

Usage (called by `make generate-chart-schema`):
    python scripts/generate_pod_chart_schemas.py \\
        --agent-pod      apps/fred-agents/config/schema/configuration.schema.json \\
        --knowledge-base libs/fred-sdk/config/schema/configuration.schema.json \\
        --charts-dir     deploy/charts
"""

import argparse
import json
import sys
from pathlib import Path

from generate_chart_schema import (
    _BOOL,
    _ENV_VAR,
    _IMAGE,
    _INT,
    _OBJECT_FREE,
    _SECURITY_CONTEXT,
    _STRING,
    _VOLUME,
    _VOLUME_MOUNT,
    _arr,
    _inline_refs,
    _load,
    _obj,
)

_SECRET = _obj(
    {
        "existingSecret": _STRING,
        "create": _BOOL,
        "data": {"type": "object", "additionalProperties": _STRING},
    }
)

_SERVICE_MONITOR = _obj(
    {
        "enabled": _BOOL,
        "labels": _OBJECT_FREE,
        "annotations": _OBJECT_FREE,
        "interval": _STRING,
        "scrapeTimeout": _STRING,
        "path": _STRING,
        "relabelings": _arr(_OBJECT_FREE),
        "metricRelabelings": _arr(_OBJECT_FREE),
    }
)


def _pod_props(configuration: dict) -> dict:
    """What both pod charts share: the image, the pod, its credentials and its file."""
    return {
        "image": _IMAGE,
        "imagePullSecrets": _arr(_obj({"name": _STRING})),
        "nameOverride": _STRING,
        "fullnameOverride": _STRING,
        "replicaCount": _INT,
        "configuration": configuration,
        "secret": _SECRET,
        "extraEnvVars": _arr(_ENV_VAR),
        "extraVolumes": _arr(_VOLUME),
        "extraVolumeMounts": _arr(_VOLUME_MOUNT),
        "podAnnotations": _OBJECT_FREE,
        "podLabels": _OBJECT_FREE,
        "podSecurityContext": _OBJECT_FREE,
        "securityContext": _SECURITY_CONTEXT,
        "resources": _obj({"limits": _OBJECT_FREE, "requests": _OBJECT_FREE}),
        "terminationGracePeriodSeconds": _INT,
        "nodeSelector": _OBJECT_FREE,
        "tolerations": _arr(_OBJECT_FREE),
        "affinity": _OBJECT_FREE,
        "topologySpreadConstraints": _arr(_OBJECT_FREE),
    }


def _chart(title: str, props: dict) -> dict:
    return {
        "$schema": "https://json-schema.org/draft-07/schema#",
        "title": title,
        "type": "object",
        "additionalProperties": False,
        # x-* keys are YAML anchors a values file may use; Helm resolves them first.
        "patternProperties": {"^x-": {}},
        "properties": props,
    }


def agent_pod(configuration: dict) -> dict:
    return _chart(
        "Fred agent pod chart values",
        {
            **_pod_props(configuration),
            "service": _obj({"port": _INT}),
            "ingress": _obj(
                {
                    "enabled": _BOOL,
                    "className": _STRING,
                    "host": _STRING,
                    "annotations": _OBJECT_FREE,
                }
            ),
            "extraConfigFiles": {
                "type": "object",
                "additionalProperties": {"type": ["string", "object"]},
            },
        },
    )


def knowledge_base(configuration: dict) -> dict:
    return _chart(
        "Fred Knowledge Base pod chart values",
        {
            **_pod_props(configuration),
            "strategy": _OBJECT_FREE,
            "publish": _obj(
                {
                    "enabled": _BOOL,
                    "backoffLimit": _INT,
                    "activeDeadlineSeconds": _INT,
                    "ttlSecondsAfterFinished": _INT,
                    "podAnnotations": _OBJECT_FREE,
                    "resources": _obj(
                        {"limits": _OBJECT_FREE, "requests": _OBJECT_FREE}
                    ),
                }
            ),
            "metricsService": _obj(
                {
                    "enabled": _BOOL,
                    "type": _STRING,
                    "annotations": _OBJECT_FREE,
                    "serviceMonitor": _SERVICE_MONITOR,
                }
            ),
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent-pod", required=True, type=Path, metavar="SCHEMA")
    parser.add_argument("--knowledge-base", required=True, type=Path, metavar="SCHEMA")
    parser.add_argument("--charts-dir", required=True, type=Path, metavar="DIR")
    args = parser.parse_args()

    for path in (args.agent_pod, args.knowledge_base):
        if not path.exists():
            print(f"ERROR: schema not found: {path}", file=sys.stderr)
            sys.exit(1)

    for chart, schema in (
        ("agent-pod", agent_pod(_inline_refs(_load(args.agent_pod)))),
        ("knowledge-base", knowledge_base(_inline_refs(_load(args.knowledge_base)))),
    ):
        output = args.charts_dir / chart / "values.schema.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        with open(output, "w") as f:
            json.dump(schema, f, indent=2)
            f.write("\n")
        print(f"Chart values schema written to {output}")


if __name__ == "__main__":
    main()
