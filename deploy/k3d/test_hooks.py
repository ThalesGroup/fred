"""Exercise product operations with fake commands, never a real cluster."""

import base64
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

FAKE = """#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
name, args = Path(sys.argv[0]).name, sys.argv[1:]
with open(os.environ["CALLS"], "a") as f:
    f.write(json.dumps([name, *args]) + "\\n")
if name == "curl": print('{"root_bootstrap_required": true}')
if name == "kubectl":
    if "deployments" in args and not os.environ.get("FRESH"):
        print("deployment/fred-agents\\ndeployment/knowledge-flow-backend\\ndeployment/knowledge-flow-worker")
    if "secret" in args and "get" in args: print(os.environ.get("CURRENT_KEY", ""))
    if "secret" in args and "patch" in args:
        p = Path(args[args.index("--patch-file") + 1])
        assert p.stat().st_mode & 0o077 == 0
        import base64
        (name, value), = json.loads(p.read_text())["data"].items()
        assert value == base64.b64encode(os.environ[name].encode()).decode()
        with open(os.environ["CALLS"] + ".patched", "a") as f: f.write(name + "\\n")
    if "configmap" in args and "get" in args:
        p = Path(os.environ["CALLS"] + ".count")
        count = int(p.read_text()) if p.exists() else 0
        p.write_text(str(count + 1))
        print(count if os.environ.get("DASHBOARD_CHANGED") else "same")
    if "apply" in args: sys.stdin.read()
"""


class HookTests(unittest.TestCase):
    def exercise(
        self, changed: bool, fresh: bool = False, brave_key: str = ""
    ) -> tuple[str, list]:
        with tempfile.TemporaryDirectory(prefix="fred configure ") as directory:
            root = Path(directory)
            (root / "deploy/k3d").mkdir(parents=True)
            (root / "deploy/grafana").mkdir()
            (root / "deploy/grafana/dashboard.json").write_text(
                '{"datasource": "${DS_PROMETHEUS}"}'
            )
            for hook in ("prepare", "finish"):
                shutil.copy(Path(__file__).with_name(hook), root / "deploy/k3d" / hook)
            fakebin = root / "bin"
            fakebin.mkdir()
            for name in ("kubectl", "curl", "getent"):
                command = fakebin / name
                command.write_text(FAKE)
                command.chmod(0o755)
            key = "test-only-secret-not-for-logs"
            env = dict(
                os.environ,
                PATH=f"{fakebin}:{os.environ['PATH']}",
                CALLS=str(root / "calls"),
                KUBE_CONTEXT="k3d-test",
                K3D_NAMESPACE="test",
                OPENAI_API_KEY=key,
                CURRENT_KEY="" if changed else base64.b64encode(key.encode()).decode(),
                DASHBOARD_CHANGED="1" if changed else "",
                FRESH="1" if fresh else "",
                WEB_RESEARCH_PROVIDER_KEY=brave_key,
            )
            output = ""
            for hook in ("prepare", "finish"):
                result = subprocess.run(
                    ["bash", str(root / "deploy/k3d" / hook)],
                    env=env,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                output += result.stdout + result.stderr
            calls = [
                json.loads(line) for line in (root / "calls").read_text().splitlines()
            ]
            for secret in filter(None, (key, brave_key)):
                self.assertNotIn(secret, output + json.dumps(calls))
            patched = root / "calls.patched"
            self.patched = patched.read_text().split() if patched.exists() else []
            self.assertNotIn(
                base64.b64encode(key.encode()).decode(), output + json.dumps(calls)
            )
            self.assertIn("get secret fred-secrets", output)
            self.assertFalse(
                any("CONTROL_PLANE_BOOTSTRAP_TOKEN" in str(c) for c in calls)
            )
            for call in calls:
                if call[0] == "kubectl":
                    self.assertEqual(call[1:3], ["--context", "k3d-test"])
            return output, calls

    def test_changed_key_and_dashboards_restart_consumers_without_logging_secrets(
        self,
    ) -> None:
        _, calls = self.exercise(True)
        self.assertTrue(any("patch" in c and "secret" in c for c in calls))
        restarts = [c for c in calls if "restart" in c]
        self.assertEqual(len(restarts), 4)
        for app in ("fred-agents", "knowledge-flow-backend", "knowledge-flow-worker"):
            self.assertTrue(any(f"deployment/{app}" in c for c in restarts))
        self.assertTrue(any("deployment/grafana" in c for c in restarts))

    def test_fresh_install_prepares_key_without_restarting_absent_consumers(
        self,
    ) -> None:
        _, calls = self.exercise(True, fresh=True)
        self.assertTrue(any("patch" in c and "secret" in c for c in calls))
        self.assertFalse(
            any("restart" in c and "deployment/grafana" not in c for c in calls)
        )

    def test_brave_key_from_environment_reaches_fred_secrets(self) -> None:
        output, _ = self.exercise(False, brave_key="test-only-brave-key")
        self.assertEqual(self.patched, ["WEB_RESEARCH_PROVIDER_KEY"])
        self.assertIn("Brave Search key written to fred-secrets", output)

    def test_unchanged_key_and_dashboards_do_not_restart(self) -> None:
        _, calls = self.exercise(False)
        self.assertFalse(any("restart" in c or "patch" in c for c in calls))


if __name__ == "__main__":
    unittest.main()
