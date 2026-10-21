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


NOTES_AS_TEMPLATE = """apiVersion: v1
kind: ConfigMap
metadata:
  name: notes
data:
  notes: {{ tpl (.Files.Get "notes.txt") . | quote }}
"""


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
        self, chart: str, values: dict, *, notes: bool = False, dependency: bool = False
    ) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as work:
            source = CHARTS / chart
            if dependency:
                # The chart as a parent chart's subchart, its values under its name.
                source = Path(work) / "parent"
                shutil.copytree(CHARTS / chart, source / "charts" / chart)
                (source / "Chart.yaml").write_text(
                    "apiVersion: v2\nname: parent\nversion: 1.0.0\n"
                )
                values = {chart: values}
            if notes:
                # helm renders NOTES.txt only on install, which needs a cluster:
                # render it as an ordinary template of a copy instead.
                source = Path(work) / chart
                shutil.copytree(CHARTS / chart, source)
                notes_file = source / "templates" / "NOTES.txt"
                (source / "notes.txt").write_text(notes_file.read_text())
                (source / "templates" / "zz-notes.yaml").write_text(NOTES_AS_TEMPLATE)
            values_file = Path(work) / "values.json"
            values_file.write_text(json.dumps(values))
            command = ["helm", "template", "release", str(source)]
            command += ["-n", "ns", "-f", str(values_file)]
            return subprocess.run(command, capture_output=True, text=True, check=False)

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

    def test_extra_env_vars_must_carry_the_m2m_secret(self):
        reference = {"secretKeyRef": {"name": "platform", "key": "k"}}
        unrelated = [{"name": "UNRELATED", "value": "x"}]
        named = [{"name": "POD_SECRET", "valueFrom": reference}]
        for chart, values in (("agent-pod", AGENT), ("knowledge-base", KNOWLEDGE_BASE)):
            with self.subTest(chart=chart):
                without = merged(values, {"secret": {"existingSecret": ""}})
                self.assert_refused(
                    chart,
                    merged(without, {"extraEnvVars": unrelated}),
                    "named POD_SECRET",
                )
                result = self.render(chart, merged(without, {"extraEnvVars": named}))
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_agent_pod_http_route(self):
        default = self.render("agent-pod", AGENT)
        self.assertEqual(default.returncode, 0, default.stderr)
        self.assertNotIn("kind: HTTPRoute", default.stdout)

        values = merged(
            AGENT,
            {
                "httpRoute": {
                    "enabled": True,
                    "parentRefs": [
                        {
                            "name": "public-gateway",
                            "namespace": "envoy-gateway-system",
                            "sectionName": "https",
                        }
                    ],
                    "hostnames": ["app.example.com"],
                    "requestTimeout": "300s",
                }
            },
        )
        result = self.render("agent-pod", values)
        self.assertEqual(result.returncode, 0, result.stderr)
        for expected in (
            "kind: HTTPRoute",
            "name: public-gateway",
            "namespace: envoy-gateway-system",
            "app.example.com",
            'value: "/my/agents/v2"',
            "name: release-agent-pod",
            "port: 80",
            'request: "300s"',
        ):
            self.assertIn(expected, result.stdout)

    def test_agent_pod_http_route_requires_gateway_and_hostname(self):
        enabled = merged(AGENT, {"httpRoute": {"enabled": True}})
        self.assert_refused("agent-pod", enabled, "httpRoute.parentRefs is required")
        gateway = merged(
            enabled, {"httpRoute": {"parentRefs": [{"name": "public-gateway"}]}}
        )
        self.assert_refused("agent-pod", gateway, "httpRoute.hostnames is required")
        self.assert_refused(
            "agent-pod",
            merged(gateway, {"httpRoute": {"hostnames": [""]}}),
            "minLength: got 0, want 1",
        )
        self.assert_refused(
            "agent-pod",
            merged(AGENT, {"httpRoute": {"hostnmes": ["app.example.com"]}}),
            "additional properties 'hostnmes' not allowed",
        )

    def test_agent_pod_base_url_is_canonical(self):
        for path in ("foo", "/foo/", "/a//b", "/a/../b"):
            with self.subTest(path=path):
                values = merged(AGENT, {"configuration": {"app": {"base_url": path}}})
                self.assert_refused("agent-pod", values, "canonical root-relative path")

    def test_long_image_tag(self):
        tag = "a" * 64
        for chart, values in (("agent-pod", AGENT), ("knowledge-base", KNOWLEDGE_BASE)):
            with self.subTest(chart=chart):
                result = self.render(chart, merged(values, {"image": {"tag": tag}}))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn(f": {tag}\n", result.stdout.replace('"', ""))

    def test_knowledge_base_accepts_pod_owned_sections(self):
        own = {"configuration": {"webdav": {"concurrency": 4}}}
        result = self.render("knowledge-base", merged(KNOWLEDGE_BASE, own))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("concurrency: 4", result.stdout)

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

    def test_both_charts_render_as_a_dependency(self):
        # Helm hands every subchart a `global` key, which the schema must accept.
        for chart, values in (("agent-pod", AGENT), ("knowledge-base", KNOWLEDGE_BASE)):
            with self.subTest(chart=chart):
                result = self.render(chart, values, dependency=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                refused = self.render(
                    chart, merged(values, {"replicas": 2}), dependency=True
                )
                self.assertNotEqual(refused.returncode, 0, refused.stdout)
                self.assertIn("additional properties 'replicas'", refused.stderr)

    def test_agent_pod_notes_give_the_registration(self):
        result = self.render("agent-pod", AGENT, notes=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("- runtime_id: my-agents", result.stdout)
        self.assertIn(
            "base_url: http://release-agent-pod.ns.svc.cluster.local:80/my/agents/v2",
            result.stdout,
        )
        self.assertIn("ingress_prefix: /my/agents/v2", result.stdout)

    def test_knowledge_base_notes_give_the_publisher(self):
        result = self.render("knowledge-base", KNOWLEDGE_BASE, notes=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        # The notes are a quoted string here: their newlines are escaped.
        self.assertIn(
            r"knowledgeBasePublishers:\n        pod:\n          prefix: my.kb",
            result.stdout,
        )

    def test_agent_pod_mounts_extra_config_files(self):
        result = self.render(
            "agent-pod",
            merged(
                AGENT, {"extraConfigFiles": {"models_catalog.yaml": {"version": "v1"}}}
            ),
        )
        self.assertIn('mountPath: "/app/config/models_catalog.yaml"', result.stdout)
        self.assertIn("models_catalog.yaml: |", result.stdout)

    def test_metrics_exposed_only_on_a_reachable_address(self):
        loopback = {"observability": {"kpi": {"prometheus": {"enabled": True}}}}
        for chart, values in (("agent-pod", AGENT), ("knowledge-base", KNOWLEDGE_BASE)):
            with self.subTest(chart=chart):
                self.assert_refused(
                    chart, merged(values, {"configuration": loopback}), "set 0.0.0.0"
                )
        reachable = {"enabled": True, "address": "0.0.0.0"}
        rendered = self.render(
            "agent-pod",
            merged(
                AGENT,
                {
                    "configuration": {
                        "observability": {"kpi": {"prometheus": reachable}}
                    }
                },
            ),
        ).stdout
        self.assertIn("containerPort: 9000", rendered)

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
