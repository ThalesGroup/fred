"""Render the real chart: manager topology and shared-config rollout regressions."""

from pathlib import Path
import subprocess
import unittest

import yaml

CHART = Path(__file__).parent / "fred"


def render(*settings, values=None):
    command = ["helm", "template", "fred-app", str(CHART), "-n", "fred"]
    if values:
        command += ["-f", str(values)]
    for setting in settings:
        command += ["--set", setting]
    return list(filter(None, yaml.safe_load_all(subprocess.check_output(command, text=True))))


def deployments(docs):
    return {d["metadata"]["name"]: d for d in docs if d["kind"] == "Deployment"}


class ManagerChartTests(unittest.TestCase):
    def test_default_topology_and_images(self):
        docs = render()
        apps = deployments(docs)
        self.assertEqual(set(apps), {"control-plane-backend", "control-plane-worker", "knowledge-flow-backend", "knowledge-flow-worker", "frontend"})
        self.assertTrue(all(d["spec"]["replicas"] == 1 for d in apps.values()))
        images = {n: d["spec"]["template"]["spec"]["containers"][0]["image"] for n, d in apps.items()}
        self.assertEqual(len(set(images.values())), 3)
        self.assertEqual(images["control-plane-backend"], images["control-plane-worker"])
        self.assertEqual(images["knowledge-flow-backend"], images["knowledge-flow-worker"])
        self.assertFalse(any(d["kind"] == "Job" and ("control-plane" in d["metadata"]["name"] or "fred-agents" in d["metadata"]["name"]) for d in docs))
        for name in ("control-plane-backend", "control-plane-worker"):
            self.assertEqual(apps[name]["spec"]["template"]["spec"]["serviceAccountName"], name)

    def test_shared_manager_configuration_and_catalog_roll_both_processes(self):
        baseline = deployments(render())
        for setting in ("configuration.scheduler.lifecycle.enabled=true", "lifecycle_policy_catalog.space_policies.purge.default.retention=P8D"):
            changed = deployments(render("applications.control-plane-backend." + setting))
            for name in ("control-plane-backend", "control-plane-worker"):
                self.assertNotEqual(baseline[name]["spec"]["template"], changed[name]["spec"]["template"], name)
            self.assertEqual(changed["control-plane-backend"]["spec"]["template"]["metadata"]["annotations"], changed["control-plane-worker"]["spec"]["template"]["metadata"]["annotations"])

    def test_common_temporal_connection_keeps_lifecycle_queue(self):
        docs = render("applications.control-plane-backend.configuration.scheduler.temporal.host=custom:7233", "applications.control-plane-backend.configuration.scheduler.temporal.namespace=custom")
        configmap = next(d for d in docs if d["kind"] == "ConfigMap" and d["metadata"]["name"] == "control-plane-backend-back")
        config = yaml.safe_load(configmap["data"]["configuration.yaml"])
        temporal = config["scheduler"]["lifecycle"]["temporal"]
        self.assertEqual(temporal["host"], "custom:7233")
        self.assertEqual(temporal["namespace"], "custom")
        self.assertEqual(temporal["task_queue"], "fred-manager-lifecycle")

    def test_unchanged_factory_values(self):
        values = CHART.resolve().parents[3] / "fred-deployment-factory/k3d-apps/fred/values.yaml"
        if not values.exists():
            self.skipTest("sibling factory checkout is unavailable")
        docs = render(values=values)
        apps = deployments(docs)
        self.assertEqual(set(apps), {"control-plane-backend", "control-plane-worker", "knowledge-flow-backend", "knowledge-flow-worker", "frontend"})
        job = next(d for d in docs if d["kind"] == "Job" and d["metadata"]["name"].startswith("control-plane-backend-migration"))
        container = job["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(container["command"] + container["args"], ["fred-manager", "migrate"])
        self.assertNotIn("volumeMounts", container)
        self.assertFalse(any(d["kind"] == "Job" and d["metadata"]["name"].startswith("control-plane-backend-scale-down") for d in docs))
        configmap = next(d for d in docs if d["kind"] == "ConfigMap" and d["metadata"]["name"] == "control-plane-backend-back")
        config = yaml.safe_load(configmap["data"]["configuration.yaml"])
        self.assertEqual(config["security"]["rebac"]["store_name"], "fred-manager")
        self.assertEqual(config["security"]["m2m"]["client_id"], "control-plane")
        self.assertEqual(config["security"]["m2m"]["secret_env_var"], "KEYCLOAK_CONTROL_PLANE_CLIENT_SECRET")
        self.assertEqual(config["app"]["port"], 8222)
        self.assertEqual(config["app"]["base_url"], "/control-plane/v1")
        self.assertEqual(config["storage"]["postgres"]["database"], "fred")
        self.assertEqual(config["scheduler"]["lifecycle"]["temporal"]["workflow_id_prefix"], "fred-manager-lifecycle")


if __name__ == "__main__":
    unittest.main()
