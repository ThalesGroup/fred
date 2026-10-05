import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "build_images", Path(__file__).with_name("build-images.py")
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class BuildImagesTests(unittest.TestCase):
    def test_content_tags_worker_mapping_and_paths_with_spaces(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fred build ") as directory:
            root = Path(directory)
            output = root / "image values"

            def capture(command: list[str], **kwargs: object) -> str:
                if command[0] == "make":
                    app = Path(command[command.index("-C") + 1]).name
                    return f"localhost:5000/fred/{app}:dev\n"
                return "sha256:" + "a" * 64

            with (
                patch.object(module.subprocess, "check_output", side_effect=capture),
                patch.object(
                    module.subprocess,
                    "run",
                    return_value=subprocess.CompletedProcess([], 0),
                ) as run,
            ):
                module.build(root, output)
                before = (output / "images.json").read_text()
                module.build(root, output)
            self.assertEqual(before, (output / "images.json").read_text())
            applications = json.loads(before)["applications"]
            self.assertEqual(len(applications), 6)
            for prefix in ("knowledge-flow", "control-plane"):
                self.assertEqual(
                    applications[f"{prefix}-backend"], applications[f"{prefix}-worker"]
                )
            self.assertEqual(
                applications["frontend"]["image"]["tag"], "k3d-aaaaaaaaaaaa"
            )
            self.assertEqual(len((output / "images.txt").read_text().splitlines()), 4)
            builds = [
                call.args[0]
                for call in run.call_args_list
                if "docker-build" in call.args[0]
            ]
            self.assertEqual(len(builds), 8)
            self.assertEqual(builds[0][3], str(root / "apps/fred-agents"))

    def test_failed_build_does_not_publish_partial_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / "images.json").write_text("previous complete build")
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
                (output / "images.json").read_text(), "previous complete build"
            )
            self.assertFalse((output / "images.txt").exists())


if __name__ == "__main__":
    unittest.main()
