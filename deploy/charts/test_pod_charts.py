"""Render the agent-pod and knowledge-base charts with helm; never a cluster."""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

CHARTS = Path(__file__).resolve().parent
M2M = {
    "realm_url": "http://keycloak:8080/realms/app",
    "client_id": "pod",
    "secret_env_var": "POD_SECRET",
}
AGENT = {
    "image": {"repository": "registry.example.com/pod", "tag": "1.0.0"},
    "secret": {"existingSecret": "pod-secrets"},
    "configuration": {
        "app": {"runtime_id": "my-agents", "base_url": "/my/agents/v2", "port": 8020},
        "security": {
            "m2m": M2M,
            "user": {"realm_url": M2M["realm_url"], "client_id": "app"},
        },
    },
}
KNOWLEDGE_BASE = {
    "image": {"repository": "registry.example.com/kb", "tag": "1.0.0"},
    "secret": {"existingSecret": "kb-secrets"},
    "configuration": {
        "app": {"runtime_id": "my-kb"},
        "knowledge_base": {
            "prefix": "my.kb",
            "control_plane_url": "http://control-plane-backend:8222/control-plane/v1",
        },
        "security": {"m2m": M2M},
    },
}


def merged(base: dict, overrides: dict) -> dict:
    result = dict(base)
    for key, value in overrides.items():
        result[key] = (
            merged(base[key], value)
            if isinstance(value, dict) and isinstance(base.get(key), dict)
            else value
        )
    return result


@unittest.skipUnless(shutil.which("helm"), "helm is not installed")
class PodChartTests(unittest.TestCase):
    def render(
        self, chart: str, values: dict, *, notes: bool = False
    ) -> subprocess.CompletedProcess:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as file:
            json.dump(values, file)
        command = [
            "helm",
            "template",
            "release",
            str(CHARTS / chart),
            "-n",
            "ns",
            "-f",
            file.name,
        ]
        if notes:
            command = [
                "helm",
                "install",
                "release",
                str(CHARTS / chart),
                "-n",
                "ns",
                "-f",
                file.name,
                "--dry-run",
            ]
        try:
            return subprocess.run(command, capture_output=True, text=True, check=False)
        finally:
            Path(file.name).unlink()

    def assert_refused(self, chart: str, values: dict, message: str) -> None:
        result = self.render(chart, values)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(message, result.stderr)

    def test_both_charts_render(self):
        for chart, values in (("agent-pod", AGENT), ("knowledge-base", KNOWLEDGE_BASE)):
            with self.subTest(chart=chart):
                result = self.render(chart, values)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_no_default_image(self):
        for chart, values in (("agent-pod", AGENT), ("knowledge-base", KNOWLEDGE_BASE)):
            with self.subTest(chart=chart):
                self.assert_refused(
                    chart,
                    merged(values, {"image": {"tag": ""}}),
                    "image.tag is required",
                )

    def test_credentials_required(self):
        for chart, values in (("agent-pod", AGENT), ("knowledge-base", KNOWLEDGE_BASE)):
            with self.subTest(chart=chart):
                self.assert_refused(
                    chart,
                    merged(values, {"secret": {"existingSecret": ""}}),
                    "credentials are required",
                )

    def test_agent_pod_without_m2m_needs_no_secret(self):
        values = merged(
            AGENT,
            {
                "secret": {"existingSecret": ""},
                "configuration": {"security": {"m2m": {"enabled": False}}},
            },
        )
        self.assertEqual(self.render("agent-pod", values).returncode, 0)

    def test_misspelled_configuration_key(self):
        values = merged(
            KNOWLEDGE_BASE, {"configuration": {"knowledge_base": {"prefx": "x"}}}
        )
        self.assert_refused(
            "knowledge-base", values, "additional properties 'prefx' not allowed"
        )
        values = merged(AGENT, {"configuration": {"app": {"runtim_id": "x"}}})
        self.assert_refused(
            "agent-pod", values, "additional properties 'runtim_id' not allowed"
        )

    def test_misspelled_chart_key(self):
        self.assert_refused(
            "agent-pod",
            merged(AGENT, {"replicas": 2}),
            "additional properties 'replicas' not allowed",
        )

    def test_agent_pod_notes_give_the_registration(self):
        result = self.render("agent-pod", AGENT, notes=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("- runtime_id: my-agents", result.stdout)
        self.assertIn(
            "base_url: http://release-agent-pod.ns.svc.cluster.local:80/my/agents/v2",
            result.stdout,
        )
        self.assertIn("ingress_prefix: /my/agents/v2", result.stdout)

    def test_agent_pod_mounts_extra_config_files(self):
        result = self.render(
            "agent-pod",
            merged(
                AGENT, {"extraConfigFiles": {"models_catalog.yaml": {"version": "v1"}}}
            ),
        )
        self.assertIn('mountPath: "/app/config/models_catalog.yaml"', result.stdout)
        self.assertIn("models_catalog.yaml: |", result.stdout)

    def test_knowledge_base_publish_job(self):
        rendered = self.render("knowledge-base", KNOWLEDGE_BASE).stdout
        self.assertIn("helm.sh/hook: post-install,post-upgrade,post-rollback", rendered)
        self.assertIn("- publish", rendered)
        self.assertIn("- run", rendered)
        off = self.render(
            "knowledge-base", merged(KNOWLEDGE_BASE, {"publish": {"enabled": False}})
        ).stdout
        self.assertNotIn("kind: Job", off)


if __name__ == "__main__":
    unittest.main()
