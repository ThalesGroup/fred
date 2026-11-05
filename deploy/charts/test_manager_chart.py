"""Render the real chart: manager topology and shared-config rollout regressions."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

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


class PreparationWorkerChartTests(unittest.TestCase):
    settings = (
        "applications.fred-agents.enabled=true",
        "applications.fred-agents-worker.enabled=true",
        "applications.control-plane-backend.configuration.platform.capability_preparation.workers.fred-agents.issuer=https://issuer.example/realm",
        "applications.control-plane-backend.configuration.platform.capability_preparation.workers.fred-agents.audience=app",
        "applications.control-plane-backend.configuration.platform.capability_preparation.workers.fred-agents.client_id=agentic",
        "applications.control-plane-backend.configuration.scheduler.lifecycle.temporal.host=temporal:7233",
        "applications.fred-agents.configuration.scheduler.temporal.host=temporal:7233",
    )

    def test_worker_inherits_api_image_credentials_and_sql_after_overlays(self):
        docs = render(
            *self.settings,
            "applications.fred-agents.image.tag=reception-content-tag",
            "applications.fred-agents.configuration.storage.postgres.database=reception",
            "applications.fred-agents.configuration.scheduler.enabled=false",
            "applications.fred-agents.extraEnvVars[0].name=KEYCLOAK_AGENTIC_CLIENT_SECRET",
            "applications.fred-agents.extraEnvVars[0].valueFrom.secretKeyRef.name=workload",
            "applications.fred-agents.extraEnvVars[0].valueFrom.secretKeyRef.key=client-secret",
            "applications.fred-agents.migration.enabled=true",
            "applications.control-plane-backend.migration.enabled=true",
        )
        apps = deployments(docs)
        api = apps["fred-agents"]["spec"]["template"]["spec"]["containers"][0]
        pod = apps["fred-agents-worker"]["spec"]["template"]["spec"]
        worker = pod["containers"][0]
        self.assertEqual(worker["image"], api["image"])
        self.assertTrue(worker["image"].endswith(":reception-content-tag"))
        self.assertEqual(worker["env"], api["env"])
        self.assertEqual(
            worker["command"], ["python", "-m", "fred_agents", "--mode", "worker"]
        )
        self.assertEqual(api["command"], ["python", "-m", "fred_agents"])
        self.assertEqual(pod["terminationGracePeriodSeconds"], 60)
        for key in ("ports", "livenessProbe", "readinessProbe", "startupProbe"):
            self.assertNotIn(key, worker)
        configs = {
            d["metadata"]["name"]: yaml.safe_load(d["data"]["configuration.yaml"])
            for d in docs
            if d["kind"] == "ConfigMap" and "configuration.yaml" in d.get("data", {})
        }
        api_config = configs["fred-agents-back"]
        worker_config = configs["fred-agents-worker-back"]
        self.assertFalse(api_config["scheduler"]["enabled"])
        self.assertTrue(worker_config["scheduler"].pop("enabled"))
        api_config["scheduler"].pop("enabled")
        self.assertEqual(worker_config, api_config)
        self.assertEqual(worker_config["storage"]["postgres"]["database"], "reception")
        self.assertEqual(
            {
                d["kind"]
                for d in docs
                if d["metadata"]["name"].startswith("fred-agents-worker")
            },
            {"Deployment", "ConfigMap", "ServiceAccount"},
        )
        jobs = {d["metadata"]["name"]: d for d in docs if d["kind"] == "Job"}
        self.assertLess(
            int(
                jobs["control-plane-backend-schema-init-1"]["metadata"]["annotations"][
                    "helm.sh/hook-weight"
                ]
            ),
            int(
                jobs["fred-agents-migration-1"]["metadata"]["annotations"][
                    "helm.sh/hook-weight"
                ]
            ),
        )

    def test_worker_can_be_paused_without_changing_api_replicas(self):
        apps = deployments(
            render(*self.settings, "applications.fred-agents-worker.replicaCount=0")
        )
        self.assertEqual(apps["fred-agents-worker"]["spec"]["replicas"], 0)
        self.assertEqual(apps["fred-agents"]["spec"]["replicas"], 1)

    def test_contract_export_keeps_migration_volume_mounts_valid(self):
        docs = render(
            *self.settings,
            "applications.control-plane-backend.workerContract.exportFromWorkerImage=true",
            "applications.control-plane-backend.migration.enabled=true",
            "applications.fred-agents.migration.enabled=true",
        )
        for resource in docs:
            if resource["kind"] not in {"Deployment", "Job"}:
                continue
            with self.subTest(resource=resource["metadata"]["name"]):
                pod = resource["spec"]["template"]["spec"]
                volumes = {volume["name"] for volume in pod.get("volumes", [])}
                for container in pod["containers"] + pod.get("initContainers", []):
                    mounts = container.get("volumeMounts", [])
                    self.assertLessEqual({mount["name"] for mount in mounts}, volumes)
                    paths = [mount["mountPath"] for mount in mounts]
                    self.assertEqual(len(paths), len(set(paths)))
        cp = deployments(docs)["control-plane-backend"]["spec"]["template"]["spec"]
        self.assertIn(
            {
                "name": "processing-contract",
                "mountPath": "/app/processing-contract",
                "readOnly": True,
            },
            cp["containers"][0]["volumeMounts"],
        )

    def test_invalid_worker_connections_and_overrides_fail_before_deployment(self):
        for setting, message in (
            (
                "applications.fred-agents.enabled=false",
                "requires applications.fred-agents.enabled",
            ),
            (
                "applications.fred-agents.configuration.app.runtime_id=unbound",
                "requires a CP",
            ),
            (
                "applications.fred-agents.configuration.scheduler.temporal.namespace=another",
                "temporal.namespace must match",
            ),
            (
                "applications.fred-agents.configuration.scheduler.temporal.host=another:7233",
                "temporal.host must match",
            ),
            ("applications.fred-agents-worker.image.tag=another", "image"),
            (
                "applications.fred-agents-worker.configuration.storage.postgres.database=another",
                "storage",
            ),
            (
                "applications.fred-agents-worker.extraEnvVars[0].name=OTHER_IDENTITY",
                "extraEnvVars",
            ),
            ("applications.fred-agents-worker.migration.enabled=true", "false"),
            ("applications.fred-agents-worker.terminationGracePeriodSeconds=10", "60"),
        ):
            with self.subTest(setting=setting):
                command = ["helm", "template", "fred-app", str(CHART)]
                for value in (*self.settings, setting):
                    command += ["--set", value]
                result = subprocess.run(command, capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)


class ManagerChartTests(unittest.TestCase):
    def test_cluster_rbac_is_disjoint_between_application_namespaces(self):
        resources = []
        for namespace in ("fred-swift", "fred-weaver"):
            docs = render("applications.fred-agents.enabled=true", namespace=namespace)
            roles = {d["metadata"]["name"] for d in docs if d["kind"] == "ClusterRole"}
            bindings = [d for d in docs if d["kind"] == "ClusterRoleBinding"]
            self.assertTrue(roles)
            for binding in bindings:
                self.assertIn(binding["roleRef"]["name"], roles)
                self.assertEqual(binding["subjects"][0]["namespace"], namespace)
            resources.append(
                {
                    (d["kind"], d["metadata"]["name"])
                    for d in docs
                    if d["kind"] in {"ClusterRole", "ClusterRoleBinding"}
                }
            )
        self.assertFalse(resources[0] & resources[1])

    def test_schema_initialization_hook_keeps_its_password_secret_reference(self):
        docs = render(
            "applications.control-plane-backend.migration.enabled=true",
            "applications.control-plane-backend.dotenv.FRED_POSTGRES_PASSWORD=fixture",
        )
        job = next(
            d
            for d in docs
            if d["kind"] == "Job"
            and d["metadata"]["name"] == "control-plane-backend-schema-init-1"
        )
        container = job["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(
            container["command"] + container["args"],
            ["control-plane", "initialize-schema"],
        )
        secret_name = container["envFrom"][0]["secretRef"]["name"]
        secret = next(
            d
            for d in docs
            if d["kind"] == "Secret" and d["metadata"]["name"] == secret_name
        )
        self.assertEqual(secret_name, "control-plane-backend-schema-init-db")
        self.assertEqual(secret["stringData"]["FRED_POSTGRES_PASSWORD"], "fixture")
        self.assertEqual(
            job["metadata"]["annotations"]["helm.sh/hook"], "pre-install,pre-upgrade"
        )

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
        self.assertEqual(len(set(images.values())), 4)
        self.assertNotEqual(
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

    def test_api_image_is_rejected_for_each_worker_group(self):
        for worker in (
            "knowledge-flow-worker",
            "knowledge-flow-worker-extraction-fast",
            "knowledge-flow-worker-extraction-medium",
            "knowledge-flow-worker-extraction-rich",
        ):
            with self.subTest(worker=worker):
                result = subprocess.run(
                    [
                        "helm",
                        "template",
                        "fred-app",
                        str(CHART),
                        "--set",
                        "applications.knowledge-flow-backend.image.repository=example/api",
                        "--set",
                        "applications.knowledge-flow-backend.image.tag=audit",
                        "--set",
                        f"applications.{worker}.enabled=true",
                        "--set",
                        f"applications.{worker}.image.repository=example/api",
                        "--set",
                        f"applications.{worker}.image.tag=audit",
                    ],
                    capture_output=True,
                    text=True,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(
                    "requires independent API and worker images", result.stderr
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

    def test_factory_weaver_values_render_this_chart(self):
        factory = CHART.resolve().parents[3] / "fred-deployment-factory"
        if not (factory / "k3d-apps/fred/values-weaver.yaml").exists() or not shutil.which(
            "helmfile"
        ):
            self.skipTest("sibling factory checkout or helmfile is unavailable")
        rendered = subprocess.check_output(
            [
                "helmfile",
                "-f",
                str(factory / "k3d-apps/fred/helmfile.yaml.gotmpl"),
                "-e",
                "weaver",
                "template",
                "--skip-deps",
            ],
            text=True,
            env=os.environ | {"DIR": str(CHART.resolve().parents[2])},
            stderr=subprocess.DEVNULL,
        )
        docs = list(filter(None, yaml.safe_load_all(rendered)))
        apps = deployments(docs)
        self.assertEqual(
            set(apps),
            {
                "control-plane-backend",
                "monitor",
                "knowledge-flow-backend",
                "knowledge-flow-worker",
                "frontend",
                "fred-agents",
                "fred-agents-worker",
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
        # The contract comes from the worker's image and configuration, without credentials.
        pod = apps["control-plane-backend"]["spec"]["template"]["spec"]
        init = pod["initContainers"][0]
        worker = apps["knowledge-flow-worker"]["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(init["image"], worker["image"])
        self.assertNotIn("env", init)
        self.assertEqual(
            {v["name"]: v.get("configMap", {}).get("name") for v in pod["volumes"] if v["name"] in ("worker-config", "processing-contract")},
            {"worker-config": "knowledge-flow-worker-back", "processing-contract": None},
        )
        self.assertTrue(
            any(d["kind"] == "Job" and d["metadata"]["name"] == "fred-app-postgres-bootstrap" for d in docs)
        )
        job = next(
            d
            for d in docs
            if d["kind"] == "Job"
            and d["metadata"]["name"].startswith("control-plane-backend-schema-init")
        )
        container = job["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(
            container["command"] + container["args"],
            ["control-plane", "initialize-schema"],
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
            config["security"]["authorized_origins"], ["http://weaver.localhost:8088"]
        )
        self.assertNotIn("rebac", config["security"])
        self.assertEqual(
            config["security"]["m2m"]["secret_env_var"],
            "KEYCLOAK_CONTROL_PLANE_CLIENT_SECRET",
        )
        self.assertEqual(config["app"]["base_url"], "/control-plane/v1")
        self.assertEqual(config["storage"]["postgres"]["database"], "fred_weaver")
        self.assertEqual(
            config["scheduler"]["lifecycle"]["temporal"]["host"], "temporal:7233"
        )


if __name__ == "__main__":
    unittest.main()
