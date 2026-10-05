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
    if "secret" in args and "get" in args: print(os.environ.get("CURRENT_KEY", ""))
    if "secret" in args and "patch" in args:
        p = Path(args[args.index("--patch-file") + 1])
        assert p.stat().st_mode & 0o077 == 0
        import base64
        assert json.loads(p.read_text())["data"]["OPENAI_API_KEY"] == base64.b64encode(os.environ["OPENAI_API_KEY"].encode()).decode()
    if "configmap" in args and "get" in args:
        p = Path(os.environ["CALLS"] + ".count")
        count = int(p.read_text()) if p.exists() else 0
        p.write_text(str(count + 1))
        print(count if os.environ.get("DASHBOARD_CHANGED") else "same")
    if "apply" in args: sys.stdin.read()
"""


class ConfigureTests(unittest.TestCase):
    def exercise(self, changed: bool) -> tuple[str, list]:
        with tempfile.TemporaryDirectory(prefix="fred configure ") as directory:
            root = Path(directory)
            (root / "deploy/k3d").mkdir(parents=True)
            (root / "deploy/grafana").mkdir()
            (root / "deploy/grafana/dashboard.json").write_text(
                '{"datasource": "${DS_PROMETHEUS}"}'
            )
            script = root / "deploy/k3d/configure.sh"
            shutil.copy(Path(__file__).with_name("configure.sh"), script)
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
            )
            result = subprocess.run(
                ["bash", str(script)], env=env, capture_output=True, text=True
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            calls = [
                json.loads(line) for line in (root / "calls").read_text().splitlines()
            ]
            output = result.stdout + result.stderr
            self.assertNotIn(key, output + json.dumps(calls))
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
        self.assertEqual(len(restarts), 2)
        self.assertTrue(
            any(
                all(
                    app in c
                    for app in (
                        "fred-agents",
                        "knowledge-flow-backend",
                        "knowledge-flow-worker",
                    )
                )
                for c in restarts
            )
        )
        self.assertTrue(any("deployment/grafana" in c for c in restarts))

    def test_unchanged_key_and_dashboards_do_not_restart(self) -> None:
        _, calls = self.exercise(False)
        self.assertFalse(any("restart" in c or "patch" in c for c in calls))


if __name__ == "__main__":
    unittest.main()
