"""Render the real chart: manager topology and shared-config rollout regressions."""

from pathlib import Path
import subprocess
import unittest

import yaml

CHART = Path(__file__).parent / "fred"


def render(*settings):
    command = ["helm", "template", "fred-app", str(CHART), "-n", "fred"]
    for setting in settings:
        command += ["--set", setting]
    return list(filter(None, yaml.safe_load_all(subprocess.check_output(command, text=True))))


def deployments(docs):
    return {d["metadata"]["name"]: d for d in docs if d["kind"] == "Deployment"}


class ManagerChartTests(unittest.TestCase):
    def test_default_topology_and_images(self):
        docs = render()
        apps = deployments(docs)
        self.assertEqual(set(apps), {"fred-manager", "fred-manager-worker", "knowledge-flow-backend", "knowledge-flow-worker", "frontend"})
        self.assertTrue(all(d["spec"]["replicas"] == 1 for d in apps.values()))
        images = {n: d["spec"]["template"]["spec"]["containers"][0]["image"] for n, d in apps.items()}
        self.assertEqual(len(set(images.values())), 3)
        self.assertEqual(images["fred-manager"], images["fred-manager-worker"])
        self.assertEqual(images["knowledge-flow-backend"], images["knowledge-flow-worker"])
        self.assertFalse(any(d["kind"] == "Job" and ("control-plane" in d["metadata"]["name"] or "fred-agents" in d["metadata"]["name"]) for d in docs))
        for name in ("fred-manager", "fred-manager-worker"):
            self.assertEqual(apps[name]["spec"]["template"]["spec"]["serviceAccountName"], name)

    def test_shared_manager_configuration_and_catalog_roll_both_processes(self):
        baseline = deployments(render())
        for setting in ("configuration.scheduler.lifecycle.enabled=true", "lifecycle_policy_catalog.space_policies.purge.default.retention=P8D"):
            changed = deployments(render("applications.fred-manager." + setting))
            for name in ("fred-manager", "fred-manager-worker"):
                self.assertNotEqual(baseline[name]["spec"]["template"], changed[name]["spec"]["template"], name)
            self.assertEqual(changed["fred-manager"]["spec"]["template"]["metadata"]["annotations"], changed["fred-manager-worker"]["spec"]["template"]["metadata"]["annotations"])


if __name__ == "__main__":
    unittest.main()
