# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
# /// script
# dependencies = ["pyyaml>=6.0"]
# ///
"""Exercise development packaging and rendered image identities without a registry."""

import json
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

import yaml

from package_dev_charts import ROOT, package, read_digests


class DevChartTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.digests = self.directory / "digests"
        self.digests.mkdir()
        self.revision = "a" * 40
        self.expected = {}
        images = json.loads((ROOT / ".github/docker-images.json").read_text())["images"]
        for index, image in enumerate(images):
            if image["publish"]:
                name = image["name"]
                self.expected[name] = f"sha256:{index:064x}"
                self.write_image(name, self.expected[name], self.revision)

    def write_image(self, name, digest, revision):
        (self.digests / f"{name}.json").write_text(
            json.dumps({"name": name, "digest": digest, "revision": revision})
        )

    def test_incomplete_or_mixed_build_cannot_be_packaged(self):
        output = self.directory / "packages"
        for fault in ("missing", "wrong-revision", "empty-digest"):
            with self.subTest(fault=fault):
                self.write_image("monitor", self.expected["monitor"], self.revision)
                if fault == "missing":
                    (self.digests / "monitor.json").unlink()
                else:
                    self.write_image(
                        "monitor",
                        "" if fault == "empty-digest" else self.expected["monitor"],
                        "b" * 40 if fault == "wrong-revision" else self.revision,
                    )
                with self.assertRaises(ValueError):
                    package(self.digests, self.revision, "5.0.0-dev.100.1", output)
                self.assertFalse(output.exists())

    def test_failed_job_retry_can_reuse_successful_image_results(self):
        self.write_image("monitor", "sha256:" + "f" * 64, self.revision)
        expected = self.expected | {"monitor": "sha256:" + "f" * 64}
        self.assertEqual(read_digests(self.digests, self.revision), expected)

    def test_packaged_chart_pins_deployments_init_containers_and_hooks(self):
        output = self.directory / "packages"
        source_values = (ROOT / "deploy/charts/fred/values.yaml").read_bytes()
        version = "5.0.0-dev.100.2"
        package(self.digests, self.revision, version, output)
        self.assertEqual(
            (ROOT / "deploy/charts/fred/values.yaml").read_bytes(), source_values
        )
        self.assertEqual(len(list(output.glob("*.tgz"))), 3)
        chart = output / f"fred-{version}.tgz"
        with tarfile.open(chart) as archive:
            inventory = json.load(archive.extractfile("fred/files/image-digests.json"))
            self.assertEqual(inventory["images"], self.expected)
            self.assertEqual(inventory["revision"], self.revision)
        for name in ("fred", "agent-pod", "knowledge-base"):
            with tarfile.open(output / f"{name}-{version}.tgz") as archive:
                metadata = yaml.safe_load(archive.extractfile(f"{name}/Chart.yaml"))
            source = yaml.safe_load(
                (ROOT / f"deploy/charts/{name}/Chart.yaml").read_text()
            )
            self.assertEqual(
                metadata["appVersion"],
                "v5-dev" if name == "fred" else source["appVersion"],
            )
            self.assertEqual(metadata["version"], version)
        rendered = subprocess.check_output(
            [
                "helm",
                "template",
                "fred",
                str(chart),
                "--set",
                "applications.fred-agents.migration.scaleDown=true",
            ],
            text=True,
        )
        seen = set()
        kinds = set()
        for document in yaml.safe_load_all(rendered):
            if not document or document["kind"] not in ("Deployment", "Job"):
                continue
            pod = document["spec"]["template"]["spec"]
            for group in ("containers", "initContainers"):
                for container in pod.get(group, []):
                    repository, digest = container["image"].split("@")
                    name = repository.rsplit("/", 1)[-1]
                    self.assertEqual(digest, self.expected[name])
                    seen.add(name)
                    kinds.add((document["kind"], group))
        self.assertEqual(seen, self.expected.keys() - {"knowledge-flow-worker-pymupdf"})
        self.assertEqual(
            kinds,
            {
                ("Deployment", "containers"),
                ("Deployment", "initContainers"),
                ("Job", "containers"),
            },
        )


if __name__ == "__main__":
    unittest.main()
