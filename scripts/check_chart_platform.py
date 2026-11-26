# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
# /// script
# dependencies = ["pyyaml>=6.0"]
# ///
"""Check the published chart's fresh-install wiring without a cluster."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "deploy/charts/fred"


class PlatformChartTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Exercise actual image overlays, namespace DNS and a non-default issuer.
        images = json.loads((ROOT / ".github/docker-images.json").read_text())["images"]
        cls.published = {i["name"] for i in images if i["publish"]}
        values = {
            "postgresBootstrap": {"enabled": True},
            "applications": {
                name: {"image": {"tag": "v5.0.0-alpha.1"}}
                for name in cls.published
                if name != "knowledge-flow-worker-pymupdf"
            },
        }
        values["applications"]["control-plane-backend"]["configuration"] = {
            "security": {
                "user": {"realm_url": "https://identity.example.test/realms/test"}
            }
        }
        with tempfile.TemporaryDirectory() as directory:
            overlay = Path(directory) / "values.json"
            overlay.write_text(json.dumps(values))
            result = subprocess.run(
                [
                    "helm",
                    "template",
                    "fred",
                    str(CHART),
                    "-n",
                    "test-v5",
                    "-f",
                    str(overlay),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        cls.objects = {
            (d["kind"], d["metadata"]["name"]): d
            for d in yaml.safe_load_all(result.stdout)
            if d
        }

    def pod(self, name, kind="Deployment"):
        return self.objects[kind, name]["spec"]["template"]["spec"]

    def config(self, name):
        return yaml.safe_load(
            self.objects["ConfigMap", f"{name}-back"]["data"]["configuration.yaml"]
        )

    def test_all_workloads_and_contract_export_use_published_images(self):
        deployments = {name for kind, name in self.objects if kind == "Deployment"}
        self.assertEqual(
            deployments,
            {
                "control-plane-backend",
                "fred-agents",
                "fred-agents-worker",
                "frontend",
                "knowledge-flow-backend",
                "knowledge-flow-worker",
                "monitor",
            },
        )
        for (kind, name), obj in self.objects.items():
            if kind not in {"Deployment", "Job"} or name == "fred-postgres-bootstrap":
                continue
            pod = obj["spec"]["template"]["spec"]
            for container in pod.get("initContainers", []) + pod["containers"]:
                image, tag = container["image"].rsplit(":", 1)
                self.assertIn(image.rsplit("/", 1)[1], self.published)
                self.assertEqual(tag, "v5.0.0-alpha.1")
        worker_image = self.pod("knowledge-flow-worker")["containers"][0]["image"]
        self.assertEqual(
            self.pod("control-plane-backend")["initContainers"][0]["image"],
            worker_image,
        )

    def test_sql_hooks_are_ordered_and_use_separate_credentials(self):
        expected = [
            ("fred-postgres-bootstrap", -20, None),
            ("control-plane-backend-schema-init-1", -10, "POSTGRES_CP_PASSWORD"),
            ("fred-agents-migration-1", 0, "POSTGRES_RUNTIME_PASSWORD"),
        ]
        for name, weight, password_key in expected:
            job = self.objects["Job", name]
            self.assertEqual(
                int(job["metadata"]["annotations"]["helm.sh/hook-weight"]), weight
            )
            pod = self.pod(name, "Job")
            self.assertFalse(pod["automountServiceAccountToken"])
            env = {e["name"]: e for e in pod["containers"][0]["env"]}
            self.assertNotIn("FRED_BOOTSTRAP_TOKEN", env)
            if password_key:
                self.assertEqual(
                    env["FRED_POSTGRES_PASSWORD"]["valueFrom"]["secretKeyRef"]["key"],
                    password_key,
                )
                self.assertNotIn(
                    "volumes", pod
                )  # pre-install cannot depend on release resources
        self.assertFalse(any("scale-down" in name for _, name in self.objects))

    def test_document_and_preparation_contracts_agree(self):
        cp = self.config("control-plane-backend")
        worker = self.config("knowledge-flow-worker")
        api = self.config("knowledge-flow-backend")
        agents = self.config("fred-agents")
        preparation = self.config("fred-agents-worker")
        for key in ("host", "namespace", "task_queue"):
            self.assertEqual(
                cp["scheduler"]["processing"]["temporal"][key],
                worker["scheduler"]["temporal"][key],
            )
        for key in ("endpoint", "bucket"):
            self.assertEqual(
                cp["scheduler"]["processing"]["derived"][key],
                api["published_artifacts"][key],
            )
            self.assertEqual(
                cp["storage"]["content"][key], worker["manager_processing"][key]
            )
        self.assertEqual(
            api["storage"]["vector_store"], worker["manager_processing"]["vector_store"]
        )
        runtime = agents["app"]["runtime_id"]
        self.assertEqual(
            cp["platform"]["runtime_catalog_sources"][0]["runtime_id"], runtime
        )
        identity = cp["platform"]["capability_preparation"]["workers"][runtime]
        self.assertEqual(identity["client_id"], agents["security"]["m2m"]["client_id"])
        for key in ("host", "namespace"):
            self.assertEqual(
                cp["scheduler"]["lifecycle"]["temporal"][key],
                preparation["scheduler"]["temporal"][key],
            )
        self.assertEqual(preparation["storage"], agents["storage"])

    def test_monitor_keeps_namespaced_read_only_access_and_issuer(self):
        pod = self.pod("monitor")
        env = {e["name"]: e for e in pod["containers"][0]["env"]}
        self.assertEqual(
            env["DATABASE_URL"]["valueFrom"]["secretKeyRef"],
            {
                "name": "fred-secrets",
                "key": "POSTGRES_MONITOR_DATABASE_URL",
            },
        )
        self.assertEqual(
            env["OIDC_ISSUER"]["value"], "https://identity.example.test/realms/test"
        )
        self.assertEqual(
            env["MONITOR_NAMESPACE"]["valueFrom"]["fieldRef"]["fieldPath"],
            "metadata.namespace",
        )
        role = self.objects["Role", "monitor-role"]
        self.assertEqual(role["metadata"]["namespace"], "test-v5")
        for rule in role["rules"]:
            self.assertEqual(rule["verbs"], ["list"])
            self.assertFalse(set(rule["resources"]) & {"secrets", "pods/log", "*"})
        self.assertFalse(
            any(kind.startswith("ClusterRole") for kind, _ in self.objects)
        )
        frontend = self.pod("frontend")["containers"][0]["env"]
        self.assertIn(
            {
                "name": "FRONTEND_MONITOR_UPSTREAM",
                "value": "http://monitor.test-v5.svc.cluster.local:8223",
            },
            frontend,
        )


if __name__ == "__main__":
    unittest.main()
