"""Keep the shared agent base aligned with the agent image it feeds."""

import re
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGENT = ROOT / "apps/fred-agents"
BASE = AGENT / "base"


def read_toml(path: Path) -> dict:
    return tomllib.loads(path.read_text())


class AgentBaseLockTest(unittest.TestCase):
    def test_shared_direct_dependencies_match(self):
        agent = read_toml(AGENT / "pyproject.toml")
        base = read_toml(BASE / "pyproject.toml")
        base_dependencies = set(base["project"]["dependencies"])
        pod_dependencies = {dependency for dependency in base_dependencies if dependency.startswith("fred-pod>")}
        self.assertEqual(len(pod_dependencies), 1)
        self.assertEqual(base_dependencies - pod_dependencies, set(agent["project"]["dependencies"]))

    def test_base_lock_reuses_agent_versions_without_capabilities(self):
        agent = read_toml(AGENT / "uv.lock")
        base = read_toml(BASE / "uv.lock")
        agent_versions = {package["name"]: package["version"] for package in agent["package"]}
        for package in base["package"]:
            name = package["name"]
            self.assertFalse(name.startswith("fred-capability-"), name)
            if name == "fred-agents-base":
                continue
            self.assertEqual(package["version"], agent_versions.get(name), name)

    def test_every_direct_dependency_is_locked(self):
        base = read_toml(BASE / "pyproject.toml")
        locked = {package["name"] for package in read_toml(BASE / "uv.lock")["package"]}
        for dependency in base["project"]["dependencies"]:
            name = re.match(r"[A-Za-z0-9_.-]+", dependency).group().lower().replace("_", "-")
            self.assertIn(name, locked)


if __name__ == "__main__":
    unittest.main()
