"""Check the broker chart's opt-in and isolation preflight without a cluster."""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

CHART = Path(__file__).resolve().parent / "fred"
DIGEST_A = "registry.example/broker@sha256:" + "a" * 64
DIGEST_B = "registry.example/python@sha256:" + "b" * 64
APPROVED = {
    "sandboxBroker": {
        "enabled": True,
        "image": DIGEST_A,
        "executionImage": DIGEST_B,
        "runtimeName": "kata-qemu",
        "networkPolicyVerified": True,
        "pidLimitVerified": True,
    }
}


@unittest.skipUnless(shutil.which("helm"), "helm is not installed")
class SandboxBrokerChartTests(unittest.TestCase):
    def render(self, overrides: dict) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as directory:
            values_file = Path(directory) / "values.json"
            values_file.write_text(json.dumps(overrides))
            return subprocess.run(
                ["helm", "template", "fred", str(CHART), "-f", str(values_file)],
                capture_output=True,
                text=True,
                check=False,
            )

    def test_disabled_by_default(self):
        rendered = self.render({})
        self.assertEqual(rendered.returncode, 0, rendered.stderr)
        self.assertNotIn("name: fred-sandbox-broker\n", rendered.stdout)

    def test_approved_profile_renders_broker_boundary(self):
        rendered = self.render(APPROVED)
        self.assertEqual(rendered.returncode, 0, rendered.stderr)
        for expected in (
            "name: fred-sandbox-broker\n",
            "name: fred-sandbox-deny-all\n",
            "name: fred-sandbox-cap\n",
            "automountServiceAccountToken: true",
            "readOnlyRootFilesystem: true",
            "SANDBOX_WARM_POOL_SIZE",
            "value: \"0\"",
        ):
            self.assertIn(expected, rendered.stdout)

    def test_unverified_or_unpinned_profile_is_rejected(self):
        for override, message in (
            ({"networkPolicyVerified": False}, "verified NetworkPolicy"),
            ({"pidLimitVerified": False}, "pod PID limits"),
            ({"executionImage": "python:3.12"}, "executionImage must be pinned"),
        ):
            with self.subTest(override=override):
                settings = APPROVED["sandboxBroker"] | override
                rendered = self.render({"sandboxBroker": settings})
                self.assertNotEqual(rendered.returncode, 0)
                self.assertIn(message, rendered.stderr)

    def test_capacity_cannot_exceed_guest_quota(self):
        rendered = self.render({"sandboxBroker": APPROVED["sandboxBroker"] | {"maxSandboxes": 21}})
        self.assertNotEqual(rendered.returncode, 0)
        self.assertIn("exceeds guest Pod quota", rendered.stderr)

        resized = self.render({"sandboxBroker": APPROVED["sandboxBroker"] | {
            "maxSandboxes": 21,
            "quota": {"pods": 24, "jobs": 24},
        }})
        self.assertEqual(resized.returncode, 0, resized.stderr)
        self.assertIn('pods: "24"', resized.stdout)

    def test_file_mount_quota_reserves_skills_pvc(self):
        files = {
            "mountProvider": "rclone_csi",
            "fileGatewayUrl": "https://gateway.example/sandbox-mount",
            "fileGatewayRevokeUrl": "https://knowledge.example/sandbox-mount",
            "fileGatewaySecret": "file-gateway",
            "fileStorageClass": "sandbox-files",
            "skillsVolume": "approved-skills",
            "maxSandboxes": 20,
        }
        rejected = self.render({"sandboxBroker": APPROVED["sandboxBroker"] | files})
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("exceeds guest file mount quota", rejected.stderr)
        accepted = self.render({"sandboxBroker": APPROVED["sandboxBroker"] | files | {
            "quota": {"persistentVolumeClaims": 21},
        }})
        self.assertEqual(accepted.returncode, 0, accepted.stderr)

    def test_optional_backends_receive_only_their_rbac(self):
        sig = self.render({"sandboxBroker": APPROVED["sandboxBroker"] | {"backend": "agent_sandbox"}})
        self.assertEqual(sig.returncode, 0, sig.stderr)
        self.assertIn("name: fred-sandbox-broker-agent-sandbox", sig.stdout)
        self.assertNotIn("name: fred-sandbox-broker-files", sig.stdout)

        files = self.render({"sandboxBroker": APPROVED["sandboxBroker"] | {
            "mountProvider": "rclone_csi",
            "fileGatewayUrl": "https://gateway.example/sandbox-mount",
            "fileGatewayRevokeUrl": "https://knowledge.example/sandbox-mount",
            "fileGatewaySecret": "file-gateway",
            "fileStorageClass": "sandbox-files",
        }})
        self.assertEqual(files.returncode, 0, files.stderr)
        self.assertIn("name: fred-sandbox-broker-files-read", files.stdout)
        self.assertNotIn("name: fred-sandbox-broker-agent-sandbox", files.stdout)


if __name__ == "__main__":
    unittest.main()
