"""Read-only monitor deployment and its independent frontend route."""
import unittest

from test_manager_chart import deployments, render


class MonitorChartTests(unittest.TestCase):
    def test_monitor_is_opt_in_and_needs_no_persistent_storage(self):
        self.assertNotIn("monitor", deployments(render()))
        docs = render("applications.monitor.enabled=true", namespace="platform")
        pod = deployments(docs)["monitor"]["spec"]["template"]["spec"]
        self.assertEqual(pod["serviceAccountName"], "monitor")
        container = pod["containers"][0]
        env = {entry["name"]: entry for entry in container["env"]}
        self.assertEqual(env["MONITOR_NAMESPACE"]["valueFrom"]["fieldRef"]["fieldPath"], "metadata.namespace")
        self.assertEqual(env["DATABASE_URL"]["valueFrom"]["secretKeyRef"]["name"], "fred-secrets")
        self.assertEqual(env["OIDC_ISSUER"]["value"], "http://keycloak:8080/realms/app")
        self.assertEqual(env["OIDC_AUDIENCE"]["value"], "app")
        self.assertFalse(any("persistentVolumeClaim" in v for v in pod.get("volumes") or []))
        role = next(d for d in docs if d["kind"] == "Role" and d["metadata"]["name"] == "monitor-role")
        self.assertEqual(role["metadata"]["namespace"], "platform")
        self.assertEqual({resource for rule in role["rules"] for resource in rule["resources"]}, {"pods", "deployments", "statefulsets", "daemonsets", "events"})
        self.assertTrue(all(rule["verbs"] == ["list"] for rule in role["rules"]))
        self.assertFalse(any(d["kind"] == "ClusterRole" and d["metadata"]["name"].startswith("monitor") for d in docs))
        frontend = deployments(docs)["frontend"]["spec"]["template"]["spec"]["containers"][0]
        upstream = next(e for e in frontend["env"] if e["name"] == "FRONTEND_MONITOR_UPSTREAM")
        self.assertEqual(upstream["value"], "http://monitor.platform.svc.cluster.local:8223")

    def test_monitor_inherits_the_real_fred_audience_and_allows_explicit_overrides(self):
        docs = render("applications.monitor.enabled=true", "applications.control-plane-backend.configuration.security.user.audience=fred-api")
        env = deployments(docs)["monitor"]["spec"]["template"]["spec"]["containers"][0]["env"]
        self.assertEqual([e["value"] for e in env if e["name"] == "OIDC_AUDIENCE"], ["fred-api"])
