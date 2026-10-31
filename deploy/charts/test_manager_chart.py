"""Render the real chart: manager topology and shared-config rollout regressions."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import yaml

CHART = Path(__file__).parent / "fred"


def render(*settings, values=None, namespace="fred"):
    command = ["helm", "template", "fred-app", str(CHART), "-n", namespace]
    if values:
        command += ["-f", str(values)]
    for setting in settings:
        command += ["--set", setting]
    return list(
        filter(None, yaml.safe_load_all(subprocess.check_output(command, text=True)))
    )


def deployments(docs):
    return {d["metadata"]["name"]: d for d in docs if d["kind"] == "Deployment"}


class ManagerChartTests(unittest.TestCase):
    def assert_manager_upstreams(self, apps, namespace):
        env = apps["frontend"]["spec"]["template"]["spec"]["containers"][0]["env"]
        for name in ("FRONTEND_CONTROL_PLANE_UPSTREAM",):
            self.assertEqual(
                [entry for entry in env if entry["name"] == name],
                [
                    {
                        "name": name,
                        "value": f"http://control-plane-backend.{namespace}.svc.cluster.local:8222",
                    }
                ],
            )

    def test_manager_upstreams_use_release_namespace_and_survive_env_replacement(self):
        for namespace in ("fred", "another-namespace"):
            with self.subTest(namespace=namespace):
                self.assert_manager_upstreams(
                    deployments(render(namespace=namespace)), namespace
                )
                self.assert_manager_upstreams(
                    deployments(
                        render(
                            "applications.frontend.env[0].name=INSTANCE_SETTING",
                            "applications.frontend.env[0].value=instance-value",
                            namespace=namespace,
                        )
                    ),
                    namespace,
                )

    def test_explicit_manager_upstream_overrides_are_preserved_without_duplicates(self):
        for field, value, expected in (
            (
                "env",
                ["value=http://external-api.example:8222"],
                {"value": "http://external-api.example:8222"},
            ),
            (
                "extraEnvVars",
                [
                    "valueFrom.configMapKeyRef.name=upstreams",
                    "valueFrom.configMapKeyRef.key=control-plane",
                ],
                {
                    "valueFrom": {
                        "configMapKeyRef": {"name": "upstreams", "key": "control-plane"}
                    }
                },
            ),
        ):
            settings = [
                f"applications.frontend.{field}[0].name=FRONTEND_CONTROL_PLANE_UPSTREAM"
            ]
            settings.extend(
                f"applications.frontend.{field}[0].{item}" for item in value
            )
            apps = deployments(render(*settings))
            env = apps["frontend"]["spec"]["template"]["spec"]["containers"][0]["env"]
            self.assertEqual(
                [
                    entry
                    for entry in env
                    if entry["name"] == "FRONTEND_CONTROL_PLANE_UPSTREAM"
                ],
                [{"name": "FRONTEND_CONTROL_PLANE_UPSTREAM", **expected}],
            )

    def test_default_topology_and_images(self):
        docs = render()
        apps = deployments(docs)
        self.assertEqual(
            set(apps),
            {
                "control-plane-backend",
                "knowledge-flow-backend",
                "knowledge-flow-worker",
                "frontend",
            },
        )
        self.assertTrue(all(d["spec"]["replicas"] == 1 for d in apps.values()))
        images = {
            n: d["spec"]["template"]["spec"]["containers"][0]["image"]
            for n, d in apps.items()
        }
        self.assertEqual(len(set(images.values())), 3)
        self.assertEqual(
            images["knowledge-flow-backend"], images["knowledge-flow-worker"]
        )
        self.assertFalse(
            any(
                d["kind"] == "Job"
                and (
                    "control-plane" in d["metadata"]["name"]
                    or "fred-agents" in d["metadata"]["name"]
                )
                for d in docs
            )
        )
        for name in ("control-plane-backend",):
            self.assertEqual(
                apps[name]["spec"]["template"]["spec"]["serviceAccountName"], name
            )

    def test_shared_manager_configuration_and_catalog_roll_both_processes(self):
        baseline = deployments(render("applications.control-plane-worker.enabled=true"))
        for setting in (
            "configuration.scheduler.lifecycle.enabled=true",
            "lifecycle_policy_catalog.space_policies.purge.default.retention=P8D",
        ):
            changed = deployments(
                render(
                    "applications.control-plane-worker.enabled=true",
                    "applications.control-plane-backend." + setting,
                )
            )
            for name in ("control-plane-backend", "control-plane-worker"):
                self.assertNotEqual(
                    baseline[name]["spec"]["template"],
                    changed[name]["spec"]["template"],
                    name,
                )
            self.assertEqual(
                changed["control-plane-backend"]["spec"]["template"]["metadata"][
                    "annotations"
                ],
                changed["control-plane-worker"]["spec"]["template"]["metadata"][
                    "annotations"
                ],
            )

    def test_common_temporal_connection_keeps_lifecycle_queue(self):
        docs = render(
            "applications.control-plane-backend.configuration.scheduler.temporal.host=custom:7233",
            "applications.control-plane-backend.configuration.scheduler.temporal.namespace=custom",
        )
        configmap = next(
            d
            for d in docs
            if d["kind"] == "ConfigMap"
            and d["metadata"]["name"] == "control-plane-backend-back"
        )
        config = yaml.safe_load(configmap["data"]["configuration.yaml"])
        temporal = config["scheduler"]["lifecycle"]["temporal"]
        self.assertEqual(temporal["host"], "custom:7233")
        self.assertEqual(temporal["namespace"], "custom")
        self.assertEqual(temporal["task_queue"], "control-plane-lifecycle")
        self.assertNotIn("temporal", config["scheduler"])

    def test_document_storage_spool_is_bounded_and_credentials_stay_references(self):
        docs = render(
            "applications.control-plane-worker.enabled=true",
            values=CHART / "examples/document-storage.yaml",
        )
        apps = deployments(docs)
        pod = apps["control-plane-backend"]["spec"]["template"]["spec"]
        spool = next(v for v in pod["volumes"] if v["name"] == "manager-document-spool")
        self.assertEqual(spool["emptyDir"]["sizeLimit"], "419430400")
        container = pod["containers"][0]
        self.assertIn(
            {
                "name": "manager-document-spool",
                "mountPath": "/tmp/control-plane-uploads",
            },
            container["volumeMounts"],
        )
        secret = next(
            e for e in container["env"] if e["name"] == "FRED_CONTENT_SECRET_KEY"
        )
        self.assertEqual(
            secret["valueFrom"]["secretKeyRef"]["name"], "manager-document-storage"
        )
        worker = apps["control-plane-worker"]["spec"]["template"]["spec"]
        self.assertFalse(
            any(v["name"] == "manager-document-spool" for v in worker["volumes"])
        )
        self.assert_manager_upstreams(apps, "fred")

    def test_k3d_profile_owns_manager_configuration_with_unchanged_factory_values(self):
        factory = CHART.resolve().parents[3] / "fred-deployment-factory"
        if not (factory / "k3d-apps/fred/values.yaml").exists() or not shutil.which(
            "helmfile"
        ):
            self.skipTest("sibling factory checkout or helmfile is unavailable")
        with tempfile.TemporaryDirectory() as out:
            env = os.environ | {
                "ENV": "secondary",
                "K3D_FACTORY_ROOT": str(factory),
                "K3D_APP_OUT": out,
                "K3D_NAMESPACE": "fred",
                "K3D_REALM_URL": "http://keycloak:8080/realms/app",
                "K3D_PUBLIC_URL": "http://fred.local",
                "K3D_WEBSOCKET_URL": "ws://fred.local",
            }
            rendered = subprocess.check_output(
                [
                    "helmfile",
                    "-f",
                    str(CHART.parent.parent / "k3d/helmfile.yaml.gotmpl"),
                    "template",
                    "--skip-deps",
                ],
                text=True,
                env=env,
                stderr=subprocess.DEVNULL,
            )
        docs = list(filter(None, yaml.safe_load_all(rendered)))
        apps = deployments(docs)
        self.assertEqual(
            set(apps),
            {
                "control-plane-backend",
                "knowledge-flow-backend",
                "knowledge-flow-worker",
                "frontend",
                "fred-agents",
            },
        )
        for deployment in apps.values():
            container = deployment["spec"]["template"]["spec"]["containers"][0]
            self.assertNotIn(
                "OPENFGA_API_TOKEN",
                {entry["name"] for entry in container.get("env", [])},
            )
        for document in docs:
            if document[
                "kind"
            ] != "ConfigMap" or "configuration.yaml" not in document.get("data", {}):
                continue
            configuration = yaml.safe_load(document["data"]["configuration.yaml"])
            self.assertNotIn("rebac", configuration.get("security", {}))
            if document["metadata"]["name"] == "knowledge-flow-backend-back":
                self.assertEqual(
                    configuration["control_plane_url"],
                    "http://control-plane-backend:8222/control-plane/v1",
                )
                self.assertTrue(configuration["security"]["m2m"]["enabled"])
                self.assertTrue(
                    configuration["security"]["delegation"]["act_for_people"]
                )
        job = next(
            d
            for d in docs
            if d["kind"] == "Job"
            and d["metadata"]["name"].startswith("control-plane-backend-migration")
        )
        container = job["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(
            container["command"] + container["args"], ["control-plane", "migrate"]
        )
        configmap = next(
            d
            for d in docs
            if d["kind"] == "ConfigMap"
            and d["metadata"]["name"] == "control-plane-backend-back"
        )
        config = yaml.safe_load(configmap["data"]["configuration.yaml"])
        # Only the manager's own sections: factory configuration for it is discarded.
        self.assertEqual(
            set(config),
            {"app", "security", "storage", "scheduler", "policies", "platform"},
        )
        self.assertEqual(set(config["storage"]), {"postgres", "content"})
        self.assertEqual(
            config["security"]["user"]["realm_url"], "http://keycloak:8080/realms/app"
        )
        self.assertEqual(
            config["security"]["authorized_origins"], ["http://fred.local"]
        )
        self.assertNotIn("rebac", config["security"])
        self.assertEqual(
            config["security"]["m2m"]["secret_env_var"],
            "KEYCLOAK_CONTROL_PLANE_CLIENT_SECRET",
        )
        self.assertEqual(config["app"]["base_url"], "/control-plane/v1")
        self.assertEqual(config["storage"]["postgres"]["database"], "fred")
        self.assertEqual(
            config["scheduler"]["lifecycle"]["temporal"]["host"], "temporal:7233"
        )


if __name__ == "__main__":
    unittest.main()
