"""Render the real chart: manager topology and shared-config rollout regressions."""

from pathlib import Path
import subprocess
import unittest

import yaml

CHART = Path(__file__).parent / "fred"


def render(*settings, values=None, namespace="fred"):
    command = ["helm", "template", "fred-app", str(CHART), "-n", namespace]
    if values:
        command += ["-f", str(values)]
    for setting in settings:
        command += ["--set", setting]
    return list(filter(None, yaml.safe_load_all(subprocess.check_output(command, text=True))))


def deployments(docs):
    return {d["metadata"]["name"]: d for d in docs if d["kind"] == "Deployment"}


class ManagerChartTests(unittest.TestCase):
    def assert_manager_upstreams(self, apps, namespace):
        env = apps["frontend"]["spec"]["template"]["spec"]["containers"][0]["env"]
        for name in ("FRONTEND_FRED_MANAGER_UPSTREAM", "FRONTEND_CONTROL_PLANE_UPSTREAM"):
            self.assertEqual([entry for entry in env if entry["name"] == name], [
                {"name": name, "value": f"http://control-plane-backend.{namespace}.svc.cluster.local:8222"}
            ])

    def test_manager_upstreams_use_release_namespace_and_survive_env_replacement(self):
        for namespace in ("fred", "another-namespace"):
            with self.subTest(namespace=namespace):
                self.assert_manager_upstreams(deployments(render(namespace=namespace)), namespace)
                self.assert_manager_upstreams(deployments(render(
                    "applications.frontend.env[0].name=INSTANCE_SETTING",
                    "applications.frontend.env[0].value=instance-value",
                    namespace=namespace,
                )), namespace)

    def test_explicit_manager_upstream_overrides_are_preserved_without_duplicates(self):
        apps = deployments(render(
            "applications.frontend.env[0].name=FRONTEND_FRED_MANAGER_UPSTREAM",
            "applications.frontend.env[0].value=http://external-api.example:8222",
            "applications.frontend.extraEnvVars[0].name=FRONTEND_CONTROL_PLANE_UPSTREAM",
            "applications.frontend.extraEnvVars[0].valueFrom.configMapKeyRef.name=upstreams",
            "applications.frontend.extraEnvVars[0].valueFrom.configMapKeyRef.key=control-plane",
        ))
        env = apps["frontend"]["spec"]["template"]["spec"]["containers"][0]["env"]
        self.assertEqual([e for e in env if e["name"] == "FRONTEND_FRED_MANAGER_UPSTREAM"], [
            {"name": "FRONTEND_FRED_MANAGER_UPSTREAM", "value": "http://external-api.example:8222"}
        ])
        self.assertEqual([e for e in env if e["name"] == "FRONTEND_CONTROL_PLANE_UPSTREAM"], [
            {"name": "FRONTEND_CONTROL_PLANE_UPSTREAM", "valueFrom": {"configMapKeyRef": {"name": "upstreams", "key": "control-plane"}}}
        ])

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

    def test_document_storage_spool_is_bounded_and_credentials_stay_references(self):
        docs = render(values=CHART / "examples/document-storage.yaml")
        apps = deployments(docs)
        pod = apps["control-plane-backend"]["spec"]["template"]["spec"]
        spool = next(v for v in pod["volumes"] if v["name"] == "manager-document-spool")
        self.assertEqual(spool["emptyDir"]["sizeLimit"], "838860800")
        container = pod["containers"][0]
        self.assertIn({"name": "manager-document-spool", "mountPath": "/tmp/fred-manager-uploads"}, container["volumeMounts"])
        secret = next(e for e in container["env"] if e["name"] == "FRED_CONTENT_SECRET_KEY")
        self.assertEqual(secret["valueFrom"]["secretKeyRef"]["name"], "manager-document-storage")
        worker = apps["control-plane-worker"]["spec"]["template"]["spec"]
        self.assertFalse(any(v["name"] == "manager-document-spool" for v in worker["volumes"]))
        self.assert_manager_upstreams(apps, "fred")

    def test_unchanged_factory_values(self):
        values = CHART.resolve().parents[3] / "fred-deployment-factory/k3d-apps/fred/values.yaml"
        if not values.exists():
            self.skipTest("sibling factory checkout is unavailable")
        docs = render(values=values)
        apps = deployments(docs)
        self.assert_manager_upstreams(apps, "fred")
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
