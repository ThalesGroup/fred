"""Offline Make/reloader checks: run with a Python containing uvicorn and watchfiles."""

import shlex
import subprocess
import threading
import tomllib
import unittest
from pathlib import Path
from uuid import uuid4

from uvicorn import Config
from uvicorn.supervisors.watchfilesreload import WatchFilesReload

ROOT = Path(__file__).resolve().parents[2]
APPS = ("fred-agents", "control-plane-backend", "knowledge-flow-backend")


class ReloadTests(unittest.TestCase):
    def test_backend_watch_scopes_and_file_changes(self) -> None:
        for app in APPS:
            with self.subTest(app=app):
                app_root = ROOT / "apps" / app
                output = subprocess.check_output(
                    [
                        "make",
                        "-s",
                        "-C",
                        str(app_root),
                        "-f",
                        "Makefile",
                        "--eval",
                        "print-reload:;@echo $(RELOAD_OPTIONS)",
                        "print-reload",
                    ],
                    text=True,
                )
                args = shlex.split(output.strip())
                dirs = [
                    Path(args[i + 1])
                    for i, arg in enumerate(args)
                    if arg == "--reload-dir"
                ]
                project = tomllib.loads((app_root / "pyproject.toml").read_text())
                sources = project["tool"]["uv"]["sources"]
                roots = [app_root] + [
                    (app_root / src["path"]).resolve()
                    for src in sources.values()
                    if "path" in src
                ]
                expected = {
                    p.parent
                    for root in roots
                    for p in root.glob("*/__init__.py")
                    if p.parent.name != "tests"
                }
                expected.add(app_root / "config")
                self.assertEqual(set(dirs), expected)
                self.assertTrue(
                    all(d.name not in {"tests", ".venv", "target"} for d in dirs)
                )
                config = Config(
                    "unused:app",
                    reload=True,
                    reload_dirs=dirs,
                    reload_includes=["*.yaml"],
                    reload_delay=0,
                )
                reloader = WatchFilesReload(config, lambda _: None, [])
                # Opening the generator starts watching; mutate disposable files only.
                probe_name = f"reload_verification_{uuid4().hex}"
                probes = [d / f"{probe_name}.py" for d in dirs if d.name != "config"]
                probes.append(app_root / "config" / f"{probe_name}.yaml")
                self.addCleanup(reloader.watcher.close)
                self.addCleanup(reloader.should_exit.set)
                self.assertEqual(set(reloader.reload_dirs), expected)
                for probe in probes:
                    self.addCleanup(probe.unlink, missing_ok=True)
                    timer = threading.Timer(
                        0.3, probe.write_text, args=("# reload probe\n",)
                    )
                    timer.start()
                    try:
                        changed = reloader.should_restart() or []
                        self.assertIn(probe, changed)
                    finally:
                        timer.join()
                reloader.should_exit.set()
                reloader.watcher.close()
                for probe in probes:
                    probe.unlink(missing_ok=True)

    def test_reload_target_flags(self) -> None:
        for app in APPS:
            app_root = ROOT / "apps" / app
            for target in ("rrun", "rrun-prod", "run-prod"):
                output = subprocess.check_output(
                    ["make", "-sn", "-C", str(app_root), target],
                    text=True,
                    stderr=subprocess.DEVNULL,
                )
                uvicorn_line = output[output.index(" run uvicorn ") :].split("\n\n")[0]
                self.assertEqual(
                    "--reload-dir" in uvicorn_line, target.startswith("rrun")
                )


if __name__ == "__main__":
    unittest.main()
