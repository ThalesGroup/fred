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
# dependencies = [
#   "pyyaml>=6.0",
# ]
# ///
"""Check the Rust chart's explicit rejection of unsupported registrations.

Upstream composition scenarios are preserved in commit 4d8f1d285 (#3211).
Usage: check_chart_registrations.py <chart dir>.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

CHART = Path(__file__).resolve().parents[1] / "deploy/charts/fred"
THANOS = {
    "ui_prefix": "/apps/thanos",
    "version": "0.1.0",
    "icon": "monitoring",
    "display_name": {"en": "ThaNOS"},
    "description": {"en": "Business monitoring."},
    "gateway": {
        "ui_upstream": "http://thanos-ui.fred.svc.cluster.local:8080",
        "service_upstream": "http://thanos-api.fred.svc.cluster.local:8111",
        "service_required": True,
    },
}


def apps(**entries: object) -> dict:
    return {"registrations": {"applications": entries}}


def publishers(**entries: object) -> dict:
    return {"registrations": {"knowledgeBasePublishers": entries}}


class ChartRegistrationTests(unittest.TestCase):
    def helm(self, *files: dict, skip_schema: bool = False) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as work:
            command = ["helm", "template", "fred", str(CHART)]
            if skip_schema:
                command.append("--skip-schema-validation")
            for index, values in enumerate(files):
                path = Path(work) / f"values-{index}.json"
                path.write_text(json.dumps(values))
                command += ["-f", str(path)]
            return subprocess.run(command, capture_output=True, text=True, check=False)

    def render(self, *files: dict) -> tuple[dict, list]:
        """The control plane's configuration and the frontend gateway's entries."""
        result = self.helm(*files)
        self.assertEqual(result.returncode, 0, result.stderr)
        documents = [d for d in yaml.safe_load_all(result.stdout) if d]
        config_map = next(
            d
            for d in documents
            if d["kind"] == "ConfigMap"
            and d["metadata"]["name"] == "control-plane-backend-back"
        )
        frontend = next(
            d
            for d in documents
            if d["kind"] == "Deployment" and d["metadata"]["name"] == "frontend"
        )
        env = frontend["spec"]["template"]["spec"]["containers"][0]["env"]
        gateway = [e["value"] for e in env if e["name"] == "FRONTEND_APPLICATIONS_JSON"]
        self.assertEqual(
            len(gateway), 1, "FRONTEND_APPLICATIONS_JSON must be set exactly once"
        )
        return yaml.safe_load(config_map["data"]["configuration.yaml"]), json.loads(
            gateway[0]
        )

    def refused(self, values: dict, message: str) -> None:
        result = self.helm(values)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(message, result.stderr)

    def test_default_registers_nothing(self):
        configuration, gateway = self.render()
        self.assertNotIn("platform", configuration)
        self.assertNotIn("knowledge_bases", configuration)
        self.assertEqual(gateway, [])

    def test_nonempty_registrations_are_refused(self):
        for values, field in (
            (apps(thanos=THANOS), "applications"),
            (publishers(**{"kb-a": {"prefix": "a"}}), "knowledgeBasePublishers"),
        ):
            with self.subTest(field=field):
                self.refused(values, field)
                result = self.helm(values, skip_schema=True)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("Non-empty registrations are not supported", result.stderr)

    def test_former_values_are_refused(self):
        control_plane = {
            "applications": {"control-plane-backend": {"configuration": {}}}
        }
        configuration = control_plane["applications"]["control-plane-backend"][
            "configuration"
        ]
        configuration["platform"] = {"application_sources": []}
        self.refused(control_plane, "platform")
        configuration.pop("platform")
        configuration["knowledge_bases"] = {"publishers": []}
        self.refused(control_plane, "knowledge_bases")
        for key in ("env", "extraEnvVars"):
            with self.subTest(key=key):
                frontend = {
                    "applications": {
                        "frontend": {
                            key: [{"name": "FRONTEND_APPLICATIONS_JSON", "value": "[]"}]
                        }
                    }
                }
                self.refused(frontend, "registrations.applications.<app_id>.gateway")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        CHART = Path(sys.argv.pop(1)).resolve()
    unittest.main()
