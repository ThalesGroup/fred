import importlib.machinery
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# build has no .py extension: it is the executable the factory runs.
loader = importlib.machinery.SourceFileLoader(
    "build", str(Path(__file__).with_name("build"))
)
spec = importlib.util.spec_from_loader("build", loader)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class BuildImagesTests(unittest.TestCase):
    def test_content_tags_worker_mapping_and_paths_with_spaces(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fred build ") as directory:
            root = Path(directory)
            output = root / "image values"

            inspection = 0

            def capture(command: list[str], **kwargs: object) -> str:
                nonlocal inspection
                if command[0] == "make":
                    app = Path(command[command.index("-C") + 1]).name
                    return f"localhost:5000/fred/{app}:dev\n"
                inspection += 1
                return json.dumps([{
                    "Id": f"sha256:{inspection:064x}",
                    "Created": f"build-{inspection}",
                    "RootFS": {"Type": "layers", "Layers": ["sha256:" + "a" * 64]},
                    "Config": {}, "Os": "linux", "Architecture": "amd64",
                }])

            with (
                patch.object(module.subprocess, "check_output", side_effect=capture),
                patch.object(
                    module.subprocess,
                    "run",
                    return_value=subprocess.CompletedProcess([], 0),
                ) as run,
            ):
                module.build(root, output)
                before = (output / "images.yaml").read_text()
                module.build(root, output)
            self.assertEqual(before, (output / "images.yaml").read_text())
            applications = json.loads(before)["applications"]
            self.assertEqual(len(applications), 6)
            for prefix in ("knowledge-flow", "control-plane"):
                self.assertEqual(
                    applications[f"{prefix}-backend"], applications[f"{prefix}-worker"]
                )
            self.assertRegex(applications["frontend"]["image"]["tag"], r"^k3d-[0-9a-f]{16}$")
            self.assertEqual(len((output / "images.txt").read_text().splitlines()), 4)
            builds = [
                call.args[0]
                for call in run.call_args_list
                if "docker-build" in call.args[0]
            ]
            self.assertEqual(len(builds), 8)
            self.assertEqual(builds[0][3], str(root / "apps/fred-agents"))

    def test_runtime_changes_get_new_tags(self) -> None:
        metadata = {
            "RootFS": {"Type": "layers", "Layers": ["sha256:" + "a" * 64]},
            "Config": {"Env": ["MODE=original"]},
            "Os": "linux", "Architecture": "amd64",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "out"

            def capture(command, **kwargs):
                if command[0] == "make":
                    return "localhost:5000/fred:dev\n"
                return json.dumps([metadata])

            def tag():
                module.build(root, output)
                return json.loads((output / "images.yaml").read_text())["applications"]["frontend"]["image"]["tag"]

            with (
                patch.object(module.subprocess, "check_output", side_effect=capture),
                patch.object(module.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)),
            ):
                original = tag()
                metadata["Config"]["Env"] = ["MODE=changed"]
                configured = tag()
                self.assertNotEqual(original, configured)
                metadata["RootFS"]["Layers"].append("sha256:" + "b" * 64)
                self.assertNotEqual(configured, tag())

    def test_failed_build_does_not_publish_partial_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / "images.yaml").write_text("previous complete build")
            with (
                patch.object(
                    module.subprocess, "check_output", return_value="fred:dev"
                ),
                patch.object(
                    module.subprocess,
                    "run",
                    side_effect=[
                        subprocess.CompletedProcess([], 1),
                        subprocess.CalledProcessError(1, "make"),
                    ],
                ) as run,
                self.assertRaises(subprocess.CalledProcessError),
            ):
                module.build(output, output)
            self.assertEqual(run.call_count, 2)
            self.assertEqual(
                (output / "images.yaml").read_text(), "previous complete build"
            )
            self.assertFalse((output / "images.txt").exists())


if __name__ == "__main__":
    unittest.main()
