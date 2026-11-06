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
"""Render the Fred chart and check what `registrations` registers.

The control plane's application_sources and knowledge_bases.publishers, and the
frontend gateway's FRONTEND_APPLICATIONS_JSON, are derived from it; several
values files must compose. Usage: check_chart_registrations.py <chart dir>.
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
EVALUATION = {
    "ui_prefix": "/apps/evaluation",
    "version": "1.2.0",
    "display_name": {"en": "Evaluation"},
    "description": {"en": "Evaluate agents."},
    "gateway": {"ui_upstream": "http://fred-evaluator-ui.fred.svc.cluster.local:8080"},
}


def apps(**entries: object) -> dict:
    return {"registrations": {"applications": entries}}


def publishers(**entries: object) -> dict:
    return {"registrations": {"knowledgeBasePublishers": entries}}


class ChartRegistrationTests(unittest.TestCase):
    def helm(self, *files: dict) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as work:
            command = ["helm", "template", "fred", str(CHART)]
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
        self.assertEqual(configuration["platform"]["application_sources"], [])
        self.assertEqual(configuration["knowledge_bases"]["publishers"], [])
        self.assertEqual(gateway, [])

    def test_files_compose_and_both_halves_agree(self):
        configuration, gateway = self.render(
            apps(thanos=THANOS), apps(evaluation=EVALUATION)
        )
        sources = configuration["platform"]["application_sources"]
        self.assertEqual([s["app_id"] for s in sources], ["evaluation", "thanos"])
        thanos = next(s for s in sources if s["app_id"] == "thanos")
        self.assertEqual(
            thanos,
            {"app_id": "thanos", **{k: v for k, v in THANOS.items() if k != "gateway"}},
        )
        self.assertEqual(
            gateway,
            [
                {"app_id": "evaluation", **EVALUATION["gateway"]},
                {"app_id": "thanos", **THANOS["gateway"]},
            ],
        )

    def test_order_of_files_does_not_change_the_rendering(self):
        first = self.helm(apps(thanos=THANOS), apps(evaluation=EVALUATION))
        second = self.helm(apps(evaluation=EVALUATION), apps(thanos=THANOS))
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout, second.stdout)

    def test_null_unregisters(self):
        configuration, gateway = self.render(
            apps(thanos=THANOS, evaluation=EVALUATION),
            apps(evaluation=None),
            publishers(**{"kb-a": {"prefix": "a"}}),
            publishers(**{"kb-a": None}),
        )
        self.assertEqual(
            [s["app_id"] for s in configuration["platform"]["application_sources"]],
            ["thanos"],
        )
        self.assertEqual([g["app_id"] for g in gateway], ["thanos"])
        self.assertEqual(configuration["knowledge_bases"]["publishers"], [])

    def test_publishers_are_registered_by_client(self):
        configuration, _ = self.render(
            publishers(**{"kb-fred.opentext": {"prefix": "fred.opentext"}}),
            publishers(**{"kb-fred.samples": {"prefix": "fred.samples"}}),
        )
        self.assertEqual(
            configuration["knowledge_bases"]["publishers"],
            [
                {"client_id": "kb-fred.opentext", "prefix": "fred.opentext"},
                {"client_id": "kb-fred.samples", "prefix": "fred.samples"},
            ],
        )

    def test_invalid_entries_are_refused(self):
        self.refused(apps(thanos={**THANOS, "ui_prefx": "/apps/thanos"}), "ui_prefx")
        self.refused(
            apps(thanos={k: v for k, v in THANOS.items() if k != "gateway"}), "gateway"
        )
        self.refused(
            apps(thanos={**THANOS, "gateway": {"service_upstream": "http://x:1"}}),
            "ui_upstream",
        )
        self.refused(apps(thanos={**THANOS, "app_id": "thanos"}), "app_id")
        self.refused(publishers(**{"kb-a": {}}), "prefix")

    def test_former_values_are_refused(self):
        control_plane = {
            "applications": {"control-plane-backend": {"configuration": {}}}
        }
        configuration = control_plane["applications"]["control-plane-backend"][
            "configuration"
        ]
        configuration["platform"] = {"application_sources": []}
        self.refused(control_plane, "registrations.applications")
        configuration.pop("platform")
        configuration["knowledge_bases"] = {"publishers": []}
        self.refused(control_plane, "registrations.knowledgeBasePublishers")
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
