"""Reset contract tests. No command in this suite reaches a real cluster."""

import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("reset_data", Path(__file__).with_name("reset_data.py"))
reset = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reset)


def configuration(name):
    manager = name in reset.MANAGER_APPS
    return {
        "storage": {
            "postgres": {"host": "postgres", "database": "fred", "username": "fred"},
            "opensearch": {"host": "https://opensearch:9200"},
            "log_store": {"type": "opensearch", "index": "app-logs-index"},
            "metadata_store": {"type": "postgres"},
            "tag_store": {"type": "postgres"},
            "resource_store": {"type": "postgres"},
            "vector_store": {"type": "opensearch", "index": "vector-index-mistral"},
            "content_storage": {
                "type": "minio",
                "endpoint": "http://seaweedfs:8333",
                "bucket_name": "control-plane-content",
            },
            "object_store": {"type": "minio", "endpoint": "http://seaweedfs:8333"},
        },
        "content_storage": {
            "type": "minio",
            "endpoint": "http://seaweedfs:8333",
            "bucket_name": "app-content",
        },
        "filesystem": {
            "type": "minio",
            "endpoint": "http://seaweedfs:8333",
            "bucket_name": "filesystem",
        },
        "security": {
            "rebac": {
                "type": "openfga",
                "api_url": "http://openfga:9080",
                "store_name": "fred-manager" if manager else "fred",
            }
        },
        "scheduler": (
            {"lifecycle": {"temporal": {"host": "temporal:7233", "namespace": "default"}}}
            if manager
            else {"temporal": {"host": "temporal:7233", "namespace": "default"}}
        ),
    }


class FakeReset(reset.Reset):
    def __init__(self):
        super().__init__()
        self.calls = []
        self.fail = None
        self.resources = {
            k: {"items": []}
            for k in (
                "deployments",
                "jobs",
                "statefulsets",
                "cronjobs",
                "horizontalpodautoscalers",
                "daemonsets",
                "replicasets",
                "replicationcontrollers",
                "pods",
            )
        }
        self.resources["secret"] = {
            "data": {
                k: "dGVzdA=="
                for k in (
                    "OPENSEARCH_ADMIN",
                    "OPENSEARCH_ADMIN_PASSWORD",
                    "OPENFGA_API_TOKEN",
                )
            }
        }
        for name in sorted(reset.APPS | reset.INFRA):
            release = "fred-manager" if name in reset.MANAGER_APPS else "fred-app" if name in reset.APPS else "fred-stack"
            self.resources["deployments"]["items"].append(
                {
                    "metadata": {
                        "name": name,
                        "namespace": "fred",
                        "uid": name,
                        "annotations": {reset.RELEASE: release},
                    },
                    "spec": {
                        "replicas": 2 if name == "fred-agents" else 1,
                        "selector": {"matchLabels": {"app": name}},
                        "template": {"spec": {"containers": [{"name": name, "image": "installed:123"}]}},
                    },
                }
            )
            self.resources["replicasets"]["items"].append(
                {
                    "metadata": {
                        "uid": name + "-rs",
                        "ownerReferences": [{"kind": "Deployment", "uid": name}],
                    }
                }
            )
            self.resources["pods"]["items"].append(
                {
                    "metadata": {
                        "name": name + "-pod",
                        "ownerReferences": [{"kind": "ReplicaSet", "uid": name + "-rs"}],
                    },
                    "status": {"phase": "Running"},
                }
            )
        self.configs = {n: {"configuration": configuration(n)} for n in reset.APPS}
        self.db_rows = "\n".join(f"{d}:{o}" for d, o in reset.DATABASES.items()) + "\n"
        self.installed_jobs = [
            {
                "kind": "Job",
                "metadata": {"name": n + "-migration-1"},
                "spec": {"template": {"spec": {"containers": [{"image": "installed:123"}]}}},
            }
            for n in ("control-plane-backend", "fred-agents", "knowledge-flow-backend")
        ]
        self.store_pages = [
            {
                "stores": [
                    {"id": "one", "name": "fred"},
                    {
                        "id": "two",
                        "name": "fred-manager-8bd7b5ba-d75f-462f-b7e6-e85df773065b",
                    },
                ]
            }
        ]
        self.file_names = ["filesystem"]

    def get(self, kind, *args):
        self.calls.append(("get", kind))
        return copy.deepcopy(self.resources[kind])

    def values(self, release):
        return {"applications": self.configs}

    def helm(self, *args):
        if args[0] == "list":
            return json.dumps(
                [
                    {"name": n, "namespace": "fred", "status": "deployed"}
                    for n in ("fred-stack", "fred-app", "fred-manager")
                ]
            )
        return "installed hooks"

    def kubectl(self, *args, data=None, timeout=180):
        self.calls.append(args)
        if self.fail and self.fail(args):
            raise reset.Refused("injected failure")
        if args[:2] == ("create", "--dry-run=client"):
            return "\n".join(json.dumps(j) for j in self.installed_jobs)
        return ""

    def sql(self, sql, database="postgres"):
        self.calls.append(("sql", database, sql))
        return self.db_rows if sql.startswith("SELECT") else ""

    def http(self, service, path, method="GET", missing=False, body=None):
        self.calls.append(("http", service, path, method))
        if service == "fga" and method == "GET":
            return self.store_pages[1 if "continuation_token" in path else 0]
        if service == "files":
            if method == "DELETE":
                self.file_names.remove(path.split("/")[2].split("?")[0])
            return {"Entries": [{"FullPath": "/buckets/" + n} for n in self.file_names]}
        return {}


class ResetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(
            os.environ,
            KUBE_CONTEXT="k3d-fred",
            K3D_CLUSTER="fred",
            K3D_NAMESPACE="fred",
            K3D_RESET_STATE_DIR=self.temp.name,
        )
        env.start()
        self.addCleanup(env.stop)
        commands = patch.object(reset, "run", return_value='[{"name":"fred"}]')
        commands.start()
        self.addCleanup(commands.stop)
        self.r = FakeReset()

    def preflight(self):
        self.r.preflight()

    def assert_read_only(self):
        self.assertFalse(
            any(c[0] in ("scale", "delete") or (c[0] == "create" and "--dry-run=client" not in c) for c in self.r.calls)
        )
        self.assertFalse(any(c[0] == "http" and c[-1] != "GET" for c in self.r.calls))
        self.assertFalse(any(c[0] == "sql" and not c[-1].startswith("SELECT") for c in self.r.calls))

    def test_real_manager_chart_configuration_accepts_typed_openfga(self):
        import yaml
        values = yaml.safe_load((Path(__file__).parents[1] / "charts/fred/values.yaml").read_text())
        names = {"control-plane-backend", "control-plane-worker"}
        for name in names:
            values["applications"][name]["configuration"]["security"]["rebac"]["api_url"] = "http://openfga:9080"
        reset.Reset().check_config(values, names)

    def test_preview_resolves_installed_hooks_without_mutation(self):
        self.preflight()
        self.assertEqual(len(self.r.jobs), 3)
        self.assert_read_only()
        self.assertFalse(self.r.state_file.exists())

    def test_integrated_manager_composition_uses_one_python_migration(self):
        retired = {"control-plane-backend", "control-plane-worker", "fred-agents"}
        for kind in ("deployments", "replicasets", "pods"):
            self.r.resources[kind]["items"] = [
                item for item in self.r.resources[kind]["items"]
                if not any(name in json.dumps(item) for name in retired)
            ]
        for deployment in self.r.resources["deployments"]["items"]:
            if deployment["metadata"]["name"] in reset.MANAGER_APPS:
                deployment["metadata"]["annotations"][reset.RELEASE] = "fred-app"
        self.r.installed_jobs = [j for j in self.r.installed_jobs if j["metadata"]["name"].startswith("knowledge-flow")]
        self.preflight()
        self.assertEqual(len(self.r.jobs), 1)
        self.assertTrue(reset.MANAGER_APPS <= self.r.state["replicas"].keys())
        self.assertFalse(retired & self.r.state["replicas"].keys())
        self.assert_read_only()

    def test_rust_control_plane_uses_two_migrations_without_agents(self):
        retired = reset.MANAGER_APPS | {"fred-agents"}
        for kind in ("deployments", "replicasets", "pods"):
            self.r.resources[kind]["items"] = [
                item for item in self.r.resources[kind]["items"]
                if not any(name in json.dumps(item) for name in retired)
            ]
        self.r.installed_jobs = [j for j in self.r.installed_jobs if not j["metadata"]["name"].startswith("fred-agents")]
        for name in ("control-plane-backend", "control-plane-worker"):
            self.r.configs[name]["configuration"] = configuration("fred-manager")
        self.preflight()
        self.assertEqual(len(self.r.jobs), 2)
        self.assertEqual(set(self.r.state["replicas"]), (reset.APPS - retired) | {"temporal"})
        self.assert_read_only()
        self.r.configs["control-plane-backend"]["configuration"]["scheduler"]["temporal"] = {"host": "external:7233"}
        with self.assertRaises(reset.Refused):
            self.preflight()

    def test_manager_worker_is_stopped_restored_and_optional(self):
        self.preflight()
        self.assertIn("fred-manager-worker", self.r.state["replicas"])
        for kind in ("deployments", "replicasets", "pods"):
            self.r.resources[kind]["items"] = [
                item for item in self.r.resources[kind]["items"]
                if not any(name in json.dumps(item) for name in reset.MANAGER_APPS)
            ]
        self.r.preflight()
        self.assert_read_only()

    def test_manager_reset_accepts_only_lifecycle_temporal_configuration(self):
        for name in reset.MANAGER_APPS:
            scheduler = self.r.configs[name]["configuration"]["scheduler"]
            self.assertNotIn("temporal", scheduler)
            self.assertIn("temporal", scheduler["lifecycle"])
        self.preflight()
        self.assert_read_only()

    def test_manager_lifecycle_external_namespace_is_refused(self):
        self.r.configs["fred-manager-worker"]["configuration"]["scheduler"]["lifecycle"]["temporal"]["namespace"] = "external"
        with self.assertRaises(reset.Refused):
            self.preflight()
        self.assert_read_only()

    def test_manager_worker_external_temporal_is_refused(self):
        self.r.configs["fred-manager-worker"]["configuration"]["scheduler"]["lifecycle"] = {
            "temporal": {"host": "external:7233"}
        }
        with self.assertRaises(reset.Refused):
            self.preflight()
        self.assert_read_only()

    def test_other_application_and_bare_pod_are_refused_before_mutation(self):
        for kind, resource in (
            ("deployments", {"metadata": {"name": "other-app", "namespace": "fred"}}),
            (
                "pods",
                {
                    "metadata": {"name": "unmanaged-writer"},
                    "status": {"phase": "Running"},
                },
            ),
            ("replicasets", {"metadata": {"name": "unmanaged-writer"}}),
            ("horizontalpodautoscalers", {"metadata": {"name": "scale-writer"}}),
        ):
            with self.subTest(kind=kind):
                self.r = FakeReset()
                self.r.resources[kind]["items"].append(resource)
                with self.assertRaises(reset.Refused):
                    self.preflight()
                self.assert_read_only()

    def test_external_or_custom_storage_is_refused(self):
        for path, value in (
            (["storage", "postgres", "host"], "prod-db"),
            (["security", "rebac", "store_name"], "other-product"),
            (["filesystem", "bucket_name"], "shared-bucket"),
            (["scheduler", "temporal", "namespace"], "shared"),
        ):
            self.r = FakeReset()
            target = self.r.configs["knowledge-flow-backend"]["configuration"]
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            with self.assertRaises(reset.Refused):
                self.preflight()
            self.assert_read_only()

    def test_openfga_inventory_is_paginated_and_rejects_foreign_stores(self):
        self.r.store_pages = [
            {"stores": [], "continuation_token": "page 2"},
            {"stores": [{"id": "x", "name": "other-product"}]},
        ]
        with self.assertRaisesRegex(reset.Refused, "other OpenFGA"):
            self.preflight()
        self.assertTrue(any("continuation_token=page%202" in c[2] for c in self.r.calls if c[0] == "http"))
        self.assert_read_only()

    def test_reset_stops_before_erasure_initializes_then_restores_without_rebuild(self):
        self.preflight()
        self.r.calls.clear()
        self.r.execute()
        calls = self.r.calls
        erasure = next(i for i, c in enumerate(calls) if c[0] == "http" and c[-1] == "DELETE")
        waits = [i for i, c in enumerate(calls) if c[:2] == ("wait", "--for=delete")]
        self.assertEqual(len(waits), len(reset.APPS) + 1)
        self.assertLess(max(waits), erasure)
        self.assertIn(("scale", "deployment/fred-agents", "--replicas=2"), calls)
        self.assertIn(("scale", "deployment/fred-manager-worker", "--replicas=0"), calls)
        self.assertIn(("scale", "deployment/fred-manager-worker", "--replicas=1"), calls)
        migrations = [i for i, c in enumerate(calls) if c[:2] == ("wait", "--for=condition=complete")]
        restore = next(i for i, c in enumerate(calls) if c[:3] == ("scale", "deployment/fred-agents", "--replicas=2"))
        self.assertLess(max(migrations), restore)
        self.assertFalse(any("keycloak" in str(c) or 'openfga"' in str(c) for c in calls if c[0] == "sql"))
        self.assertFalse(self.r.state_file.exists())

    def test_saved_replicas_survive_retry_with_missing_database_and_failed_job(self):
        self.preflight()
        self.r.state_file.write_text(json.dumps(self.r.state))
        self.r.db_rows = self.r.db_rows.replace("fred:fred\n", "")
        self.r.resources["jobs"]["items"] = [
            {
                "metadata": {
                    "uid": "failed-job",
                    "namespace": "fred",
                    "name": "fred-data-reset-migration-0",
                    "labels": {"fred.local/reset": "migration"},
                },
                "status": {"failed": 1},
            }
        ]
        for d in self.r.resources["deployments"]["items"]:
            if d["metadata"]["name"] in reset.APPS | {"temporal"}:
                d["spec"]["replicas"] = 0
        self.preflight()
        self.assertEqual(self.r.state["replicas"]["fred-agents"], 2)
        self.r.execute()
        self.assertIn(("scale", "deployment/fred-agents", "--replicas=2"), self.r.calls)

    def test_stop_does_not_wait_for_retained_migration_job_pods(self):
        self.r.resources["pods"]["items"].append(
            {
                "metadata": {
                    "name": "old-migration",
                    "labels": {"app": "control-plane-backend"},
                    "ownerReferences": [{"kind": "Job", "uid": "old-job"}],
                },
                "status": {"phase": "Succeeded"},
            }
        )
        self.preflight()
        self.r.stop()
        waits = [c for c in self.r.calls if c[:2] == ("wait", "--for=delete")]
        self.assertEqual(len(waits), len(reset.APPS) + 1)
        self.assertFalse(any("old-migration" in str(c) for c in waits))

    def test_partially_successful_job_with_active_writer_is_refused(self):
        self.r.resources["jobs"]["items"] = [
            {
                "metadata": {"name": "writer"},
                "spec": {"completions": 2},
                "status": {"succeeded": 1, "active": 1},
            }
        ]
        with self.assertRaisesRegex(reset.Refused, "unfinished Jobs"):
            self.preflight()
        self.assert_read_only()

    def test_retry_job_deletion_waits_for_dependent_pods_before_clear(self):
        self.preflight()
        self.r.calls.clear()
        self.r.execute()
        deletion = [i for i, c in enumerate(self.r.calls) if c[:2] == ("delete", "job")]
        clear = next(i for i, c in enumerate(self.r.calls) if c[0] == "http" and c[-1] == "DELETE")
        self.assertTrue(deletion)
        self.assertLess(deletion[2], clear)
        for i in deletion:
            self.assertIn("--cascade=foreground", self.r.calls[i])

    def test_missing_database_without_resume_is_refused(self):
        self.r.db_rows = ""
        with self.assertRaisesRegex(reset.Refused, "database"):
            self.preflight()

    def test_changed_image_refuses_resume(self):
        self.preflight()
        self.r.state_file.write_text(json.dumps(self.r.state))
        self.r.resources["deployments"]["items"][0]["spec"]["template"]["spec"]["containers"][0]["image"] = "changed"
        with self.assertRaisesRegex(reset.Refused, "deployments changed"):
            self.preflight()
        self.assert_read_only()

    def test_migration_failure_never_restores_fred(self):
        self.preflight()
        self.r.fail = lambda args: args[:2] == ("wait", "--for=condition=complete")
        self.r.calls.clear()
        with self.assertRaisesRegex(reset.Refused, "injected"):
            self.r.execute()
        self.assertTrue(self.r.state_file.exists())
        self.assertFalse(
            any(c[0] == "scale" and c[1] != "deployment/temporal" and c[2] != "--replicas=0" for c in self.r.calls)
        )

    def test_main_without_confirmation_never_executes(self):
        with (
            patch.object(reset, "Reset", return_value=self.r),
            patch.dict(os.environ, K3D_RESET_CONFIRM=""),
            patch.object(self.r, "execute") as execute,
        ):
            reset.main()
            execute.assert_not_called()
        self.assert_read_only()

    def test_unwritable_resume_state_does_not_stop_any_service(self):
        with (
            patch.object(reset, "Reset", return_value=self.r),
            patch.dict(os.environ, K3D_RESET_CONFIRM="reset"),
            patch.object(Path, "write_text", side_effect=OSError("disk full")),
            self.assertRaises(OSError),
        ):
            reset.main()
        self.assert_read_only()

    def test_concurrent_reset_is_refused(self):
        with (Path(self.temp.name) / "reset.lock").open("w") as lock:
            reset.fcntl.flock(lock, reset.fcntl.LOCK_EX)
            with (
                patch.object(reset, "Reset", return_value=self.r),
                self.assertRaises(BlockingIOError),
            ):
                reset.main()
        self.assertEqual(self.r.calls, [])

    def test_main_cleans_up_after_restore_readiness_failure(self):
        self.r.fail = lambda args: (
            args[:3] == ("rollout", "status", "deployment/fred-agents")
            and ("scale", "deployment/fred-agents", "--replicas=2") in self.r.calls
        )
        with (
            patch.object(reset, "Reset", return_value=self.r),
            patch.dict(os.environ, K3D_RESET_CONFIRM="reset"),
            self.assertRaises(reset.Refused),
        ):
            reset.main()
        for name in reset.APPS:
            last = [c for c in self.r.calls if c[:2] == ("scale", "deployment/" + name)][-1]
            self.assertEqual(last[2], "--replicas=0")
        self.assertTrue(self.r.state_file.exists())


if __name__ == "__main__":
    unittest.main()
