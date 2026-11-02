"""Render the real chart and inspect SQL ownership and hook ordering."""

import unittest
from pathlib import Path

from test_manager_chart import deployments, render


class PostgresBoundaryTests(unittest.TestCase):
    def test_bootstrap_is_opt_in_and_consumers_have_distinct_secret_keys(self):
        docs = render(
            "applications.monitor.enabled=true",
            "applications.fred-agents.enabled=true",
            "applications.knowledge-flow-backend.enabled=true",
            "applications.knowledge-flow-worker.enabled=true",
        )
        self.assertFalse(
            any("postgres-bootstrap" in d["metadata"]["name"] for d in docs)
        )
        expected = {
            "control-plane-backend": "POSTGRES_CP_PASSWORD",
            "knowledge-flow-backend": "POSTGRES_KF_PASSWORD",
            "knowledge-flow-worker": "POSTGRES_KF_PASSWORD",
            "fred-agents": "POSTGRES_RUNTIME_PASSWORD",
            "monitor": "POSTGRES_MONITOR_DATABASE_URL",
        }
        apps = deployments(docs)
        for app, key in expected.items():
            env = apps[app]["spec"]["template"]["spec"]["containers"][0]["env"]
            name = "DATABASE_URL" if app == "monitor" else "FRED_POSTGRES_PASSWORD"
            values = [item for item in env if item["name"] == name]
            self.assertEqual(len(values), 1)
            self.assertEqual(
                values[0]["valueFrom"]["secretKeyRef"],
                {"name": "fred-secrets", "key": key},
            )

    def test_bootstrap_precedes_cp_then_runtime_and_embeds_canonical_sql(self):
        docs = render(
            "postgresBootstrap.enabled=true",
            "applications.fred-agents.enabled=true",
            "applications.control-plane-backend.migration.enabled=true",
            "applications.fred-agents.migration.enabled=true",
        )
        jobs = {d["metadata"]["name"]: d for d in docs if d["kind"] == "Job"}
        self.assertEqual(
            int(
                jobs["fred-app-postgres-bootstrap"]["metadata"]["annotations"][
                    "helm.sh/hook-weight"
                ]
            ),
            -20,
        )
        self.assertEqual(
            int(
                jobs["control-plane-backend-schema-init-1"]["metadata"]["annotations"][
                    "helm.sh/hook-weight"
                ]
            ),
            -10,
        )
        self.assertEqual(
            int(
                jobs["fred-agents-migration-1"]["metadata"]["annotations"][
                    "helm.sh/hook-weight"
                ]
            ),
            0,
        )
        config = next(
            d
            for d in docs
            if d["kind"] == "ConfigMap"
            and d["metadata"]["name"] == "fred-app-postgres-bootstrap"
        )
        source = Path(__file__).resolve().parents[1] / "postgres/bootstrap.sql"
        self.assertEqual(
            config["data"]["bootstrap.sql"].rstrip(), source.read_text().rstrip()
        )
        for name, role, schema in [
            ("control-plane-backend-schema-init-1", "fred_cp", "control_plane"),
            ("fred-agents-migration-1", "fred_runtime", "runtime"),
        ]:
            env = jobs[name]["spec"]["template"]["spec"]["containers"][0]["env"]
            values = {item["name"]: item.get("value") for item in env}
            self.assertIn("://" + role + ":", values["DATABASE_URL"])
            self.assertEqual(values["DATABASE_SCHEMA"], schema)


if __name__ == "__main__":
    unittest.main()
